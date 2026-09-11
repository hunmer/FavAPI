"""下载工作器：后台循环串行执行下载队列（yt-dlp / videodl 子进程）。"""
import asyncio
import logging
import shutil
import sys

from app import config
from app.services import download_store
from app.utils import now_iso

logger = logging.getLogger("favapi.downloader")

CHECK_INTERVAL = 2            # 队列扫描间隔（秒）
PROGRESS_WRITE_INTERVAL = 0.5  # 进度落库最小间隔（秒）

DOWNLOADS_DIR = config.DATA_DIR / "downloads"

_task: asyncio.Task | None = None
_running: dict[str, asyncio.subprocess.Process] = {}  # download_id -> 正在执行的子进程


async def start():
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run_forever())
        logger.info("下载工作器已启动（每 %ss 扫描一次队列）", CHECK_INTERVAL)


async def stop():
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    for proc in _running.values():
        proc.kill()
    _running.clear()
    logger.info("下载工作器已停止")


async def _run_forever():
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("下载循环异常")
        await asyncio.sleep(CHECK_INTERVAL)


async def tick():
    """取最早的一条 pending 任务执行（串行，避免并发下载互相挤占带宽）。"""
    row = await download_store.next_pending()
    if row is None:
        return
    await download_store.update_download(
        row["download_id"], status="running", started_at=now_iso(), progress="启动下载器..."
    )
    try:
        await _run_one(row)
    except Exception:
        logger.exception("下载任务 %s 执行异常", row["download_id"])
        await download_store.update_download(
            row["download_id"], status="failed",
            error_message="内部错误，详见服务日志", finished_at=now_iso(),
        )


def _resolve_command(downloader: str) -> list[str] | None:
    exe = shutil.which(downloader)
    if exe:
        return [exe]
    if downloader == "yt-dlp":
        # pip 安装了包但 PATH 里没有 exe 入口时兜底
        return [sys.executable, "-m", "yt_dlp"]
    return None


async def _run_one(row: dict):
    download_id, url = row["download_id"], row["url"]
    out_dir = DOWNLOADS_DIR / (row.get("platform") or "misc")
    out_dir.mkdir(parents=True, exist_ok=True)

    base = _resolve_command(row["downloader"])
    if base is None:
        # videodl 的 PyPI 发布包名为 videofetch（github.com/CharlesPikachu/videodl）
        pkg = {"yt-dlp": "yt-dlp", "videodl": "videofetch"}[row["downloader"]]
        await download_store.update_download(
            download_id, status="failed", finished_at=now_iso(),
            error_message=f"未找到 {row['downloader']} 可执行文件，请先安装：pip install {pkg}",
        )
        return

    if row["downloader"] == "yt-dlp":
        cmd = [*base, "--newline", "--no-playlist",
               "-o", str(out_dir / "%(title).80s.%(ext)s"), url]
        cwd = None
    else:
        cmd = [*base, "-i", url]
        cwd = out_dir

    logger.info("下载开始 %s：%s", download_id, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    _running[download_id] = proc
    tail: list[str] = []
    try:
        loop = asyncio.get_running_loop()
        last_write = 0.0
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            tail.append(line)
            tail = tail[-10:]
            if loop.time() - last_write >= PROGRESS_WRITE_INTERVAL:
                await download_store.update_download(download_id, progress=line[-200:])
                last_write = loop.time()
        returncode = await proc.wait()

        # 取消：cancel() 已把状态置为 canceled，这里不覆盖
        cur = await download_store.get_download(download_id)
        if cur and cur["status"] == "canceled":
            return
        if returncode == 0:
            await download_store.update_download(
                download_id, status="success", progress="下载完成",
                output_path=str(out_dir), finished_at=now_iso(),
            )
            logger.info("下载完成 %s（%s）", download_id, url)
        else:
            await download_store.update_download(
                download_id, status="failed", output_path=str(out_dir),
                error_message="\n".join(tail)[-500:] or f"退出码 {returncode}",
                finished_at=now_iso(),
            )
            logger.warning("下载失败 %s（退出码 %s）：%s", download_id, returncode, "\n".join(tail))
    finally:
        _running.pop(download_id, None)


async def cancel(download_id: str) -> bool:
    """终止正在执行的任务（标记 canceled 并杀掉子进程）。"""
    proc = _running.get(download_id)
    if proc is None:
        return False
    await download_store.update_download(
        download_id, status="canceled", progress="已取消", finished_at=now_iso()
    )
    proc.kill()
    return True
