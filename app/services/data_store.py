"""抓取结果与任务记录的持久化。"""
import json

from app.database import db
from app.utils import now_iso


# ---------- contents / favorites ----------

async def upsert_contents(platform: str, account_id: str, items: list[dict]):
    """抓取成功后先写内容主表（存在则更新，保留 first_seen_at）。"""
    now = now_iso()
    for it in items:
        await db.execute(
            """INSERT INTO contents (content_id, platform, account_id, title, description,
                 author_id, author_name, cover_url, duration, statistics, raw_data,
                 first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(platform, content_id) DO UPDATE SET
                 account_id = excluded.account_id,
                 title = excluded.title,
                 description = excluded.description,
                 author_id = excluded.author_id,
                 author_name = excluded.author_name,
                 cover_url = excluded.cover_url,
                 duration = excluded.duration,
                 statistics = excluded.statistics,
                 raw_data = excluded.raw_data,
                 last_seen_at = excluded.last_seen_at""",
            (
                it["content_id"], platform, account_id, it.get("title"), it.get("description"),
                it.get("author_id"), it.get("author_name"), it.get("cover_url"),
                it.get("duration"), it.get("statistics"), it.get("raw_data"), now, now,
            ),
        )


async def save_fetch_result(account: dict, items: list[dict]) -> dict:
    """PRD 写入策略：upsert contents → 写 favorites 关系。返回统计。"""
    account_id, platform = account["account_id"], account["platform"]
    before = await db.query_one(
        "SELECT COUNT(*) AS n FROM favorites WHERE account_id = ? AND platform = ?",
        (account_id, platform),
    )

    await upsert_contents(platform, account_id, items)
    now = now_iso()
    for it in items:
        await db.execute(
            """INSERT OR IGNORE INTO favorites (account_id, platform, content_id,
                   fav_media_id, fav_title, collected_at, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                account_id, platform, it["content_id"],
                it.get("fav_media_id") or "", it.get("fav_title") or "",
                it.get("collected_at"), now,
            ),
        )

    after = await db.query_one(
        "SELECT COUNT(*) AS n FROM favorites WHERE account_id = ? AND platform = ?",
        (account_id, platform),
    )
    return {
        "result_count": len(items),
        "new_favorites": (after["n"] if after else 0) - (before["n"] if before else 0),
    }


_CONTENT_URL_TEMPLATES = {
    "douyin": "https://www.douyin.com/video/{content_id}",
    "bilibili": "https://www.bilibili.com/video/{content_id}",
    "xiaohongshu": "https://www.xiaohongshu.com/explore/{content_id}",
}


async def list_favorites(
    account_id: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """favorites JOIN contents，按抓取时间倒序。"""
    where, params = [], []
    if account_id:
        where.append("f.account_id = ?")
        params.append(account_id)
    if platform:
        where.append("f.platform = ?")
        params.append(platform)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    total_row = await db.query_one(
        f"SELECT COUNT(*) AS n FROM favorites f {where_sql}", tuple(params)
    )
    rows = await db.query_all(
        f"""SELECT f.account_id, f.content_id, f.platform, f.fav_media_id, f.fav_title,
                   f.collected_at, f.fetched_at,
                   c.title, c.author_name, c.cover_url, c.duration, c.statistics,
                   c.tags, c.tagged_at
            FROM favorites f LEFT JOIN contents c
              ON c.content_id = f.content_id AND c.platform = f.platform
            {where_sql}
            ORDER BY f.fetched_at DESC, f.id DESC
            LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )

    items = []
    for r in rows:
        try:
            statistics = json.loads(r.get("statistics") or "{}")
        except (TypeError, json.JSONDecodeError):
            statistics = {}
        try:
            tags = json.loads(r.get("tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            tags = []
        items.append({
            "content_id": r["content_id"],
            "account_id": r.get("account_id"),
            "platform": r["platform"],
            "title": r.get("title"),
            "author_name": r.get("author_name"),
            "cover_url": r.get("cover_url"),
            "duration": r.get("duration"),
            "statistics": statistics,
            "fav_media_id": r.get("fav_media_id") or None,
            "fav_title": r.get("fav_title") or None,
            "collected_at": r.get("collected_at"),
            "fetched_at": r.get("fetched_at"),
            "url": _CONTENT_URL_TEMPLATES.get(r["platform"], "").format(content_id=r["content_id"]) or None,
            "tags": [str(t) for t in tags] if isinstance(tags, list) else [],
            "tagged_at": r.get("tagged_at"),
        })
    return {"total": total_row["n"] if total_row else 0, "items": items, "limit": limit, "offset": offset}


# ---------- fetch_tasks ----------

async def create_task(task_id: str, account_id: str, platform: str, action: str, params: dict):
    await db.execute(
        """INSERT INTO fetch_tasks (task_id, account_id, platform, action, request_params, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        (task_id, account_id, platform, action, json.dumps(params or {}, ensure_ascii=False)),
    )


async def update_task(task_id: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    await db.execute(
        f"UPDATE fetch_tasks SET {cols} WHERE task_id = ?",
        (*fields.values(), task_id),
    )


def task_row_out(row: dict) -> dict:
    out = dict(row)
    try:
        out["request_params"] = json.loads(out.get("request_params") or "{}")
    except (TypeError, json.JSONDecodeError):
        out["request_params"] = {}
    return out


async def get_task(task_id: str) -> dict | None:
    row = await db.query_one("SELECT * FROM fetch_tasks WHERE task_id = ?", (task_id,))
    return task_row_out(row) if row else None


async def list_tasks(limit: int = 50, account_id: str | None = None) -> list[dict]:
    if account_id:
        rows = await db.query_all(
            "SELECT * FROM fetch_tasks WHERE account_id = ? ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (account_id, limit),
        )
    else:
        rows = await db.query_all(
            "SELECT * FROM fetch_tasks ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)
        )
    return [task_row_out(r) for r in rows]
