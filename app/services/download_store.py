"""下载队列（downloads）的持久化。"""
from app.database import db
from app.services.data_store import _CONTENT_URL_TEMPLATES
from app.utils import new_id, now_iso

DOWNLOADERS = ("yt-dlp", "videodl")


def content_url(platform: str, content_id: str) -> str:
    """按平台模板生成原站地址（与收藏列表的 url 字段同源）。"""
    return _CONTENT_URL_TEMPLATES.get(platform, "").format(content_id=content_id)


async def create_download(platform: str, content_id: str, title: str = "",
                          url: str = "", downloader: str = "yt-dlp") -> dict:
    if downloader not in DOWNLOADERS:
        raise ValueError(f"downloader 仅支持 {' / '.join(DOWNLOADERS)}")
    url = url.strip() or content_url(platform, content_id)
    if not url:
        raise ValueError(f"平台 {platform} 无原站地址模板，请显式传入 url")

    # 幂等：同 url + downloader 已在队列中（未完成）则直接返回已有任务
    row = await db.query_one(
        "SELECT * FROM downloads WHERE url = ? AND downloader = ? AND status IN ('pending', 'running')",
        (url, downloader),
    )
    if row:
        return row

    row = {
        "download_id": new_id("dl"),
        "platform": platform,
        "content_id": content_id,
        "title": title,
        "url": url,
        "downloader": downloader,
        "status": "pending",
        "progress": None,
        "output_path": None,
        "error_message": None,
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
    }
    await db.execute(
        """INSERT INTO downloads (download_id, platform, content_id, title, url, downloader,
               status, progress, output_path, error_message, created_at, started_at, finished_at)
           VALUES (:download_id, :platform, :content_id, :title, :url, :downloader,
                   :status, :progress, :output_path, :error_message, :created_at, :started_at, :finished_at)""",
        row,
    )
    return row


async def list_downloads() -> list[dict]:
    return await db.query_all("SELECT * FROM downloads ORDER BY created_at DESC, download_id DESC")


async def get_download(download_id: str) -> dict | None:
    return await db.query_one("SELECT * FROM downloads WHERE download_id = ?", (download_id,))


async def update_download(download_id: str, **fields) -> dict | None:
    allowed = ("status", "progress", "output_path", "error_message", "started_at", "finished_at")
    values = {k: v for k, v in fields.items() if k in allowed}
    if values:
        cols = ", ".join(f"{k} = ?" for k in values)
        await db.execute(f"UPDATE downloads SET {cols} WHERE download_id = ?",
                         (*values.values(), download_id))
    return await get_download(download_id)


async def next_pending() -> dict | None:
    return await db.query_one(
        "SELECT * FROM downloads WHERE status = 'pending' ORDER BY created_at ASC, download_id ASC LIMIT 1"
    )


async def reset_download(download_id: str) -> dict | None:
    """失败/取消后重新入队。"""
    return await update_download(
        download_id, status="pending", progress=None, error_message=None,
        started_at=None, finished_at=None,
    )


async def delete_download(download_id: str) -> bool:
    cur = await db.execute("DELETE FROM downloads WHERE download_id = ?", (download_id,))
    return cur.rowcount > 0
