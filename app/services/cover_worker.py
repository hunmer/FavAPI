"""封面图本地化：独立队列把收藏封面下载到 data/covers，防 CDN 签名链接过期。

与下载工作器完全隔离：不写 downloads 表（不进下载结果 UI）、不占用下载并发；
优先复用 aria2c RPC（与平台下载共用一个 aria2 进程），未安装/失败时回落 httpx 直下。
"""
import asyncio
import logging
import re
from pathlib import Path

import httpx

from app import config
from app.database import db

logger = logging.getLogger("favapi.covers")

QUEUE_CONCURRENCY = 2    # 封面下载并发（独立于主下载队列设置）
ARIA2_TIMEOUT = 120      # 单张封面 aria2 终态等待上限（秒）
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_queue: asyncio.Queue | None = None
_workers: list[asyncio.Task] = []
_startup_task: asyncio.Task | None = None
_seen: set[tuple[str, str]] = set()  # 已入队/执行中的 (platform, content_id)，防重复


def covers_dir() -> Path:
    return config.DATA_DIR / "covers"


def api_cover_url(platform: str, content_id: str) -> str:
    """封面统一读取入口（GET /api/v1/covers/...），本地已缓存回文件、否则跳远程。"""
    return f"/api/v1/covers/{platform}/{content_id}"


def _safe_id(value: str) -> str:
    return re.sub(r"[^\w.-]+", "_", str(value).strip())[:120] or "_"


def _ext_from_url(url: str) -> str:
    ext = re.split(r"[?#]", url, 1)[0].rsplit(".", 1)
    ext = f".{ext[-1].lower()}" if len(ext) == 2 else ""
    return ext if re.fullmatch(r"\.\w{1,5}", ext) else ".jpg"


def cover_path(platform: str, content_id: str) -> Path | None:
    """已落盘的封面文件路径（按 content_id 前缀匹配任意扩展名）；无则 None。"""
    folder = covers_dir() / _safe_id(platform)
    if not folder.exists():
        return None
    return next(iter(sorted(folder.glob(f"{_safe_id(content_id)}.*"))), None)


async def start():
    global _queue, _workers, _startup_task
    if _workers:
        return
    _queue = asyncio.Queue()
    for _ in range(QUEUE_CONCURRENCY):
        _workers.append(asyncio.create_task(_run_worker()))
    # 启动即自动续跑未完成的封面本地化（无需手动点补齐按钮）
    _startup_task = asyncio.create_task(_startup_backfill())
    logger.info("封面下载队列已启动（并发 %s）", QUEUE_CONCURRENCY)


async def _startup_backfill():
    """错开启动高峰后核对一次，缺失封面入队续跑。"""
    global _startup_task
    try:
        await asyncio.sleep(5)
        stats = await backfill()
        if stats["missing"]:
            logger.info("启动补齐：发现 %s 张缺失封面，已入队 %s 张（共 %s 张）",
                        stats["missing"], stats["enqueued"], stats["total"])
    except Exception:
        logger.exception("启动封面补齐失败")
    finally:
        _startup_task = None


async def stop():
    global _queue, _workers, _startup_task
    if _startup_task is not None:
        _startup_task.cancel()
        try:
            await _startup_task
        except asyncio.CancelledError:
            pass
        _startup_task = None
    for t in _workers:
        t.cancel()
    for t in _workers:
        try:
            await t
        except asyncio.CancelledError:
            pass
    _workers.clear()
    _queue = None


def enqueue(platform: str, content_id: str, url: str) -> bool:
    """入队一张封面；已在队列/执行中返回 False。"""
    if _queue is None or not str(url).startswith("http"):
        return False
    key = (str(platform), str(content_id))
    if key in _seen:
        return False
    _seen.add(key)
    _queue.put_nowait((str(platform), str(content_id), str(url)))
    return True


def queue_size() -> int:
    return _queue.qsize() if _queue is not None else 0


async def _run_worker():
    while True:
        platform, content_id, url = await _queue.get()
        try:
            await _download_one(platform, content_id, url)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("封面下载异常：%s/%s", platform, content_id)
        finally:
            _queue.task_done()
            _seen.discard((platform, content_id))  # 成败都解除去重，失败允许重试


async def _download_one(platform: str, content_id: str, url: str):
    existing = cover_path(platform, content_id)
    if existing is not None:  # 之前已下载过（如重抓更新了签名链接），补齐标记即可
        await _mark_localized(platform, content_id, existing)
        return

    folder = covers_dir() / _safe_id(platform)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_id(content_id)}{_ext_from_url(url)}"
    dest = folder / filename
    if await _fetch(url, dest):
        for old in folder.glob(f"{_safe_id(content_id)}.*"):  # 清掉旧扩展名残留
            if old != dest:
                old.unlink(missing_ok=True)
        await _mark_localized(platform, content_id, dest)
        logger.info("封面已本地化 %s/%s", platform, content_id)


async def _mark_localized(platform: str, content_id: str, path: Path):
    await db.execute(
        "UPDATE contents SET cover_file = ? WHERE platform = ? AND content_id = ?",
        (f"{_safe_id(platform)}/{path.name}", platform, content_id),
    )


async def _fetch(url: str, dest: Path) -> bool:
    from app.services import aria2_service

    if aria2_service.installed():
        try:
            gid = await aria2_service.add(url, dest.parent, dest.name, {"User-Agent": _UA})
            if (await aria2_service.wait_bare(gid, ARIA2_TIMEOUT)
                    and dest.is_file() and dest.stat().st_size > 0):
                return True
            dest.unlink(missing_ok=True)  # 失败残留的半成品
        except Exception as exc:
            logger.debug("封面 aria2 下载失败（回落 httpx）：%s %s", url, exc)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        if resp.content:
            dest.write_bytes(resp.content)
            return True
    except Exception as exc:
        logger.debug("封面下载失败：%s %s", url, exc)
    return False


async def backfill() -> dict:
    """核对库内 cover_file 与磁盘实际文件（丢失的清标记），缺失封面入队补齐。"""
    rows = await db.query_all(
        "SELECT platform, content_id, cover_url, cover_file FROM contents"
        " WHERE cover_url IS NOT NULL AND cover_url != ''"
    )
    missing = reset = enqueued = 0
    for r in rows:
        if r.get("cover_file"):
            if (covers_dir() / r["cover_file"]).is_file():
                continue
            await db.execute(
                "UPDATE contents SET cover_file = NULL WHERE platform = ? AND content_id = ?",
                (r["platform"], r["content_id"]),
            )
            reset += 1
        missing += 1
        if enqueue(r["platform"], r["content_id"], r["cover_url"]):
            enqueued += 1
    return {"total": len(rows), "missing": missing, "reset": reset,
            "enqueued": enqueued, "queue_size": queue_size()}
