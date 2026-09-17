"""下载工作器：后台循环执行下载队列（yt-dlp / videodl 子进程），支持并发与暂停。"""
import asyncio
import logging
import shutil
import sys
from pathlib import Path

from app import config
from app.services import download_store
from app.services.app_settings import load_settings
from app.utils import now_iso

logger = logging.getLogger("favapi.downloader")

CHECK_INTERVAL = 2            # 队列扫描间隔（秒）
PROGRESS_WRITE_INTERVAL = 0.5  # 进度落库最小间隔（秒）

# videodl 专用解析客户端映射（装好 videodl 后自动生效；未映射平台走其通用解析器）
VIDEODL_CLIENTS = {
    "bilibili": "BilibiliVideoClient",
    "douyin": "SnapAnyVideoClient",
    "xiaohongshu": "SnapAnyVideoClient",
}

# 平台 → Cookies 域名（注入 yt-dlp 时只保留对应平台的登录态）
_PLATFORM_COOKIE_DOMAINS = {
    "bilibili": ("bilibili.com",),
    "douyin": ("douyin.com",),
    "xiaohongshu": ("xiaohongshu.com",),
    "youtube": ("youtube.com", "google.com"),
}

_task: asyncio.Task | None = None
_running: dict[str, asyncio.subprocess.Process] = {}  # download_id -> 正在执行的子进程


def downloads_root() -> Path:
    """下载根目录：设置里可改（SettingsView「下载位置」），默认 data/downloads。"""
    custom = str(load_settings().get("download_dir") or "").strip()
    return Path(custom) if custom else config.DATA_DIR / "downloads"


def _concurrency() -> int:
    try:
        return max(1, min(3, int(load_settings().get("download_concurrency") or 1)))
    except (TypeError, ValueError):
        return 1


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
    inflight: set[asyncio.Task] = set()
    while True:
        try:
            inflight = {t for t in inflight if not t.done()}
            while len(inflight) < _concurrency():
                row = await download_store.next_pending()
                if row is None:
                    break
                await download_store.update_download(
                    row["download_id"], status="running", started_at=now_iso(), progress="启动下载器..."
                )
                inflight.add(asyncio.create_task(_run_one(row)))
        except asyncio.CancelledError:
            for t in inflight:
                t.cancel()
            raise
        except Exception:
            logger.exception("下载循环异常")
        await asyncio.sleep(CHECK_INTERVAL)


def _resolve_command(downloader: str) -> list[str] | None:
    exe = shutil.which(downloader)
    if exe:
        return [exe]
    if downloader == "yt-dlp":
        # pip 安装了包但 PATH 里没有 exe 入口时兜底
        return [sys.executable, "-m", "yt_dlp"]
    return None


async def _write_cookies_file(download_id: str, account_id: str | None, platform: str) -> Path | None:
    """把账号 cookie 快照写成 Netscape 格式供 yt-dlp 使用（无快照/无匹配域名返回 None）。"""
    if not account_id:
        return None
    from app.services import account_manager

    account = await account_manager.get_account(account_id)
    if account is None:
        return None
    cookies = ((account.get("extra") or {}).get("cookies") or {}).get("cookies") or []
    domains = _PLATFORM_COOKIE_DOMAINS.get(platform)
    if domains:
        cookies = [c for c in cookies if any(d in (c.get("domain") or "") for d in domains)]
    if not cookies:
        return None

    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c.get("domain") or ""
        # domain 以 . 开头表示对该站点所有子域生效
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        expires = max(int(c.get("expires") or 0), 0)  # 会话 cookie(-1) 落为 0
        secure = bool(c.get("secure")) or domain.endswith(("youtube.com", "google.com"))
        lines.append("\t".join([
            domain, flag, c.get("path") or "/", "TRUE" if secure else "FALSE", str(expires),
            c.get("name") or "", c.get("value") or "",
        ]))
    tmp = downloads_root() / ".cookies" / f"{download_id}.cookies.txt"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n".join(lines) + "\n", "utf-8")
    return tmp


def _log_file(download_id: str) -> Path:
    """每个下载任务一份日志：downloads/.logs/{download_id}.log（重试追加，保留历史）。"""
    return downloads_root() / ".logs" / f"{download_id}.log"


def _append_log(download_id: str, text: str):
    path = _log_file(download_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{text}\n")


def read_log(download_id: str) -> str:
    try:
        return _log_file(download_id).read_text("utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def delete_log(download_id: str) -> None:
    _log_file(download_id).unlink(missing_ok=True)


async def _run_one(row: dict):
    download_id, url = row["download_id"], row["url"]
    try:
        await _execute(row)
    except Exception as exc:
        logger.exception("下载任务 %s 执行异常", download_id)
        _append_log(download_id, f"[{now_iso()}] 内部错误：{exc}")
        await download_store.update_download(
            download_id, status="failed",
            error_message="内部错误，详见下载日志", finished_at=now_iso(),
        )


async def _execute(row: dict):
    download_id, url, platform = row["download_id"], row["url"], row.get("platform") or ""
    out_dir = downloads_root() / (platform or "misc")
    out_dir.mkdir(parents=True, exist_ok=True)

    base = _resolve_command(row["downloader"])
    if base is None:
        # videodl 的 PyPI 发布包名为 videofetch（github.com/CharlesPikachu/videodl）
        pkg = {"yt-dlp": "yt-dlp", "videodl": "videofetch"}[row["downloader"]]
        _append_log(download_id, f"[{now_iso()}] 未找到 {row['downloader']} 可执行文件，请先安装：pip install {pkg}")
        await download_store.update_download(
            download_id, status="failed", finished_at=now_iso(),
            error_message=f"未找到 {row['downloader']} 可执行文件，请先安装：pip install {pkg}",
        )
        return

    cookies_file = None
    if row["downloader"] == "yt-dlp":
        cmd = [*base, "--newline", "--no-playlist",
               "-o", str(out_dir / "%(title).80s.%(ext)s"), url]
        cookies_file = await _write_cookies_file(download_id, row.get("account_id"), platform)
        if cookies_file is not None:
            cmd += ["--cookies", str(cookies_file)]
            logger.info("任务 %s 已注入账号 %s 的 Cookies（%s）",
                        download_id, row.get("account_id"), cookies_file.name)
        cwd = None
    else:
        cmd = [*base, "-i", url]
        client = VIDEODL_CLIENTS.get(platform)
        if client:
            cmd += ["-a", client]
        cwd = out_dir

    logger.info("下载开始 %s：%s", download_id, " ".join(cmd))
    log_path = _log_file(download_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a", encoding="utf-8")
    log.write(f"\n===== [{now_iso()}] 开始下载（{row['downloader']}） {url} =====\n命令：{' '.join(cmd)}\n")
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
            log.write(f"{line}\n")
            log.flush()
            if loop.time() - last_write >= PROGRESS_WRITE_INTERVAL:
                await download_store.update_download(download_id, progress=line[-200:])
                last_write = loop.time()
        returncode = await proc.wait()

        # 暂停/取消：对应操作已写入终态，这里不覆盖
        cur = await download_store.get_download(download_id)
        if cur and cur["status"] in ("canceled", "paused"):
            action = "取消" if cur["status"] == "canceled" else "暂停"
            log.write(f"[{now_iso()}] 任务被{action}，进程已终止\n")
            return
        if returncode == 0:
            await download_store.update_download(
                download_id, status="success", progress="下载完成",
                output_path=str(out_dir), finished_at=now_iso(),
            )
            log.write(f"[{now_iso()}] 下载完成，输出目录：{out_dir}\n")
            logger.info("下载完成 %s（%s）", download_id, url)
        else:
            await download_store.update_download(
                download_id, status="failed", output_path=str(out_dir),
                error_message="\n".join(tail)[-500:] or f"退出码 {returncode}",
                finished_at=now_iso(),
            )
            tail_text = "\n".join(tail)
            log.write(f"[{now_iso()}] 下载失败（退出码 {returncode}），最近输出：\n{tail_text}\n")
            logger.warning("下载失败 %s（退出码 %s）：%s", download_id, returncode, tail_text)
    finally:
        log.close()
        _running.pop(download_id, None)
        if cookies_file is not None:
            cookies_file.unlink(missing_ok=True)


async def terminate(download_id: str) -> bool:
    """终止正在执行的子进程（状态由调用方决定：暂停或取消）。"""
    proc = _running.get(download_id)
    if proc is None:
        return False
    proc.kill()
    return True


async def cancel(download_id: str) -> bool:
    """取消正在执行的任务（标记 canceled 并杀掉子进程）。"""
    proc = _running.get(download_id)
    if proc is None:
        return False
    await download_store.update_download(
        download_id, status="canceled", progress="已取消", finished_at=now_iso()
    )
    proc.kill()
    return True
