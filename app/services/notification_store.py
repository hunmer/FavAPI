"""通知中心（notifications）的持久化：后台任务完成等事件落地与已读管理。"""
import logging

from app.database import db
from app.utils import new_id, now_iso

logger = logging.getLogger("favapi.notification")

MAX_KEEP = 200  # 通知保留上限，插入时清理更早的旧通知


async def create_notification(
    type_: str, title: str, detail: str = "", task_id: str | None = None
) -> None:
    await db.execute(
        """INSERT INTO notifications (notification_id, type, title, detail, task_id, read, created_at)
           VALUES (:notification_id, :type, :title, :detail, :task_id, 0, :created_at)""",
        {
            "notification_id": new_id("ntf"),
            "type": type_,
            "title": title,
            "detail": detail,
            "task_id": task_id,
            "created_at": now_iso(),
        },
    )
    await db.execute(
        """DELETE FROM notifications WHERE notification_id NOT IN (
               SELECT notification_id FROM notifications ORDER BY created_at DESC LIMIT ?)""",
        (MAX_KEEP,),
    )


async def list_notifications(limit: int = 50) -> list[dict]:
    return await db.query_all(
        "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
    )


async def unread_count() -> int:
    row = await db.query_one("SELECT COUNT(*) AS n FROM notifications WHERE read = 0")
    return (row or {}).get("n") or 0


async def mark_all_read() -> int:
    cur = await db.execute("UPDATE notifications SET read = 1 WHERE read = 0")
    return cur.rowcount


async def clear_notifications() -> int:
    cur = await db.execute("DELETE FROM notifications")
    return cur.rowcount
