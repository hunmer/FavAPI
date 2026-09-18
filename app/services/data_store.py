"""抓取结果与任务记录的持久化。"""
import asyncio
import json

from app.database import db
from app.utils import now_iso

# 作品发布日期（YYYY-MM-DD，本地时区）：各平台发布时间字段不一，均为 epoch 秒。
# douyin=create_time / bilibili=ctime / wechat=createTime；xiaohongshu 接口不提供（为 NULL）。
_PUBLISH_DATE_SQL = (
    "date(COALESCE(json_extract(c.raw_data, '$.create_time'),"
    " json_extract(c.raw_data, '$.ctime'),"
    " json_extract(c.raw_data, '$.createTime')), 'unixepoch', 'localtime')"
)


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


async def save_fetch_result(account: dict, items: list[dict], source: str = "") -> dict:
    """PRD 写入策略：upsert contents → 写 favorites 关系。返回统计。

    source 为本次抓取的入库来源标记（favorites.source，空 = 收藏列表）。
    existing_ids：本批中 favorites 已有的 content_id（供前端区分新增/已存在）。
    """
    account_id, platform = account["account_id"], account["platform"]
    before = await db.query_one(
        "SELECT COUNT(*) AS n FROM favorites WHERE account_id = ? AND platform = ?",
        (account_id, platform),
    )

    existing_ids: set[str] = set()
    for start in range(0, len(items), 500):  # IN 子句分块，避开 SQLite 变量数上限
        chunk = items[start:start + 500]
        placeholders = ",".join("?" * len(chunk))
        rows = await db.query_all(
            f"SELECT content_id FROM favorites "
            f"WHERE account_id = ? AND platform = ? AND content_id IN ({placeholders})",
            (account_id, platform, *(it["content_id"] for it in chunk)),
        )
        existing_ids.update(r["content_id"] for r in rows)

    await upsert_contents(platform, account_id, items)

    # 封面本地化：新入库封面交后台队列下载（已缓存/在队列中的自动跳过）
    from app.services import cover_worker
    for it in items:
        if it.get("cover_url"):
            cover_worker.enqueue(platform, it["content_id"], it["cover_url"])

    now = now_iso()
    for it in items:
        await db.execute(
            """INSERT OR IGNORE INTO favorites (account_id, platform, content_id,
                   fav_media_id, fav_title, source, collected_at, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account_id, platform, it["content_id"],
                it.get("fav_media_id") or "", it.get("fav_title") or "",
                source or "", it.get("collected_at"), now,
            ),
        )

    after = await db.query_one(
        "SELECT COUNT(*) AS n FROM favorites WHERE account_id = ? AND platform = ?",
        (account_id, platform),
    )
    return {
        "result_count": len(items),
        "new_favorites": (after["n"] if after else 0) - (before["n"] if before else 0),
        "existing_ids": existing_ids,
    }


async def purge_orphan_contents(ids: list[str] | None = None) -> int:
    """清理不再被任何收藏关系引用的 contents 行。

    ids 为空列表时直接返回；限定 ids 时只在这些内容中清理（仍被其他账号/
    收藏夹/来源引用的保留）；ids=None 时全库清理（favorites 已清空的场景，
    等价于清空全部 contents）。分块提交规避 SQLite 变量数上限。
    """
    orphan_sql = """DELETE FROM contents WHERE {}NOT EXISTS
        (SELECT 1 FROM favorites f WHERE f.content_id = contents.content_id)"""
    if ids is None:
        cur = await db.execute(orphan_sql.format(""))
        return cur.rowcount or 0
    total = 0
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        ph = ", ".join("?" for _ in chunk)
        cur = await db.execute(
            orphan_sql.format(f"content_id IN ({ph}) AND "), tuple(chunk)
        )
        total += cur.rowcount or 0
    return total


async def delete_favorites(refs: list[dict]) -> dict:
    """批量删除收藏关系行，并联动清理不再被引用的 contents 行。

    refs: [{account_id, platform, content_id}]，按三元组精确删除。
    executemany 一次提交（全选数千条时避免逐条往返）。
    """
    rows = [(r.get("account_id"), r.get("platform"), r.get("content_id")) for r in refs]
    cur = await db.executemany(
        "DELETE FROM favorites WHERE account_id = ? AND platform = ? AND content_id = ?",
        rows,
    )
    contents_deleted = await purge_orphan_contents([r[2] for r in rows])
    return {"deleted": cur.rowcount or 0, "contents_deleted": contents_deleted}


async def clear_favorites(account_id: str | None = None) -> dict:
    """一键清空收藏关系行并联动清理 contents（account_id 为空时清空全部账号）。"""
    if account_id:
        affected = [
            r["content_id"]
            for r in await db.query_all(
                "SELECT DISTINCT content_id FROM favorites WHERE account_id = ?", (account_id,)
            )
        ]
        cur = await db.execute("DELETE FROM favorites WHERE account_id = ?", (account_id,))
        contents_deleted = await purge_orphan_contents(affected)
    else:
        cur = await db.execute("DELETE FROM favorites")
        # favorites 已全部清空，全库清理即清空全部 contents
        contents_deleted = await purge_orphan_contents()
    return {"deleted": cur.rowcount or 0, "contents_deleted": contents_deleted}


_CONTENT_URL_TEMPLATES = {
    "douyin": "https://www.douyin.com/video/{content_id}",
    "bilibili": "https://www.bilibili.com/video/{content_id}",
    "xiaohongshu": "https://www.xiaohongshu.com/explore/{content_id}",
    # YouTube 收藏的是播放列表（playlistId），watch?v= 打不开
    "youtube": "https://www.youtube.com/playlist?list={content_id}",
    "kuaishou": "https://www.kuaishou.com/short-video/{content_id}",
}


def _item_detail_url(platform: str, content_id: str, raw: dict) -> str | None:
    """按平台拼条目详情页 URL；拼不出可靠链接的平台返回 None。

    tiktok / threads 的 content_id（数字 id/pk）无法独立成链，需从
    raw_data 里补作者 handle / 帖子 shortcode。
    """
    if platform == "tiktok":
        handle = str((raw.get("author") or {}).get("uniqueId") or "").strip()
        return f"https://www.tiktok.com/@{handle}/video/{content_id}" if handle else None
    if platform == "threads":
        code = str(raw.get("code") or raw.get("shortcode") or "").strip()
        username = str((raw.get("user") or {}).get("username") or "").strip()
        return f"https://www.threads.com/@{username}/post/{code}" if code and username else None
    template = _CONTENT_URL_TEMPLATES.get(platform, "")
    return template.format(content_id=content_id) or None


async def list_favorites(
    account_id: str | None = None,
    platform: str | None = None,
    tag: str | None = None,
    folder: str | None = None,
    author: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    pub_start: str | None = None,
    pub_end: str | None = None,
    tags: list[str] | None = None,
    q: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """favorites JOIN contents，按抓取时间倒序；tag 基于 contents.tags JSON 数组精确匹配。

    服务端过滤（与前端过滤面板语义一致）：
    - folder/author/source 精确匹配，空值占位（'默认收藏夹'/'—'/'收藏列表'）匹配 NULL 或空串
    - date_start/date_end 按 fetched_at 前 10 位（YYYY-MM-DD）闭区间比较，可只填一端
    - tags 多标签 OR；q 模糊匹配标题/作者/标签
    """
    where, params = [], []
    if account_id:
        where.append("f.account_id = ?")
        params.append(account_id)
    if platform:
        where.append("f.platform = ?")
        params.append(platform)
    if tag:
        where.append("EXISTS (SELECT 1 FROM json_each(c.tags) WHERE json_each.value = ?)")
        params.append(tag)
    if folder:
        if folder == "默认收藏夹":
            where.append("(f.fav_title IS NULL OR f.fav_title = '')")
        else:
            where.append("f.fav_title = ?")
            params.append(folder)
    if source and source != "收藏列表":
        where.append("COALESCE(NULLIF(f.source, ''), '收藏列表') = ?")
        params.append(source)
    if author:
        if author == "—":
            where.append("(c.author_name IS NULL OR c.author_name = '')")
        else:
            where.append("c.author_name = ?")
            params.append(author)
    if date_start:
        where.append("substr(f.fetched_at, 1, 10) >= ?")
        params.append(date_start)
    if date_end:
        where.append("substr(f.fetched_at, 1, 10) <= ?")
        params.append(date_end)
    if pub_start or pub_end:
        # 发布时间缺失的内容（如小红书）在启用发布时间过滤时排除
        where.append(f"{_PUBLISH_DATE_SQL} IS NOT NULL")
        if pub_start:
            where.append(f"{_PUBLISH_DATE_SQL} >= ?")
            params.append(pub_start)
        if pub_end:
            where.append(f"{_PUBLISH_DATE_SQL} <= ?")
            params.append(pub_end)
    if tags:
        placeholders = ",".join("?" for _ in tags)
        where.append(f"EXISTS (SELECT 1 FROM json_each(c.tags) WHERE json_each.value IN ({placeholders}))")
        params.extend(tags)
    if q:
        like = f"%{q}%"
        where.append(
            "(c.title LIKE ? OR c.author_name LIKE ? OR"
            " EXISTS (SELECT 1 FROM json_each(c.tags) WHERE json_each.value LIKE ?))"
        )
        params.extend([like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    total_row = await db.query_one(
        f"""SELECT COUNT(*) AS n FROM favorites f
            LEFT JOIN contents c ON c.content_id = f.content_id AND c.platform = f.platform
            {where_sql}""",
        tuple(params),
    )
    rows = await db.query_all(
        f"""SELECT f.account_id, f.content_id, f.platform, f.fav_media_id, f.fav_title,
                   f.source, f.collected_at, f.fetched_at,
                   c.title, c.author_name, c.cover_url, c.cover_file, c.duration, c.statistics,
                   c.raw_data, c.tags, c.tagged_at
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
        raw = {}
        try: raw = json.loads(r.get("raw_data") or "{}")
        except (TypeError, json.JSONDecodeError): pass
        source_url = raw.get("url") or raw.get("locationLabel")
        items.append({
            "content_id": r["content_id"],
            "account_id": r.get("account_id"),
            "platform": r["platform"],
            "title": r.get("title"),
            "author_name": r.get("author_name"),
            "cover_url": (
                f"/api/v1/covers/{r['platform']}/{r['content_id']}"
                if r.get("cover_file") else r.get("cover_url")
            ),
            "duration": r.get("duration"),
            "statistics": statistics,
            "fav_media_id": r.get("fav_media_id") or None,
            "fav_title": r.get("fav_title") or None,
            "source": r.get("source") or None,
            "collected_at": r.get("collected_at"),
            "fetched_at": r.get("fetched_at"),
            "url": source_url or _item_detail_url(r["platform"], r["content_id"], raw),
            "description": raw.get("content") or None,
            "tags": [str(t) for t in tags] if isinstance(tags, list) else [],
            "tagged_at": r.get("tagged_at"),
        })
    return {"total": total_row["n"] if total_row else 0, "items": items, "limit": limit, "offset": offset}


async def favorite_facets(account_id: str | None = None, folder: str | None = None) -> dict:
    """过滤面板候选值：全量总数、各账号收藏数、收藏夹/作者候选及计数。

    folders 按账号收敛；authors 按账号+收藏夹收敛（与前端联动逻辑一致）。
    占位值与 toScrapedItem 对齐：空收藏夹 → '默认收藏夹'，空作者 → '—'。
    """
    base, params = [], []
    if account_id:
        base.append("f.account_id = ?")
        params.append(account_id)
    where_sql = f"WHERE {' AND '.join(base)}" if base else ""

    total_row, accounts_rows, folder_rows, source_rows = await asyncio.gather(
        db.query_one(f"SELECT COUNT(*) AS n FROM favorites f {where_sql}", tuple(params)),
        db.query_all(
            f"SELECT f.account_id AS id, COUNT(*) AS count FROM favorites f {where_sql} GROUP BY f.account_id ORDER BY count DESC",
            tuple(params),
        ),
        db.query_all(
            f"""SELECT COALESCE(NULLIF(f.fav_title, ''), '默认收藏夹') AS name, COUNT(*) AS count
                FROM favorites f {where_sql} GROUP BY name ORDER BY count DESC""",
            tuple(params),
        ),
        db.query_all(
            f"""SELECT COALESCE(NULLIF(f.source, ''), '收藏列表') AS name, COUNT(*) AS count
                FROM favorites f {where_sql} GROUP BY name ORDER BY count DESC""",
            tuple(params),
        ),
    )
    author_where, author_params = list(base), list(params)
    if folder:
        author_where.append("COALESCE(NULLIF(f.fav_title, ''), '默认收藏夹') = ?")
        author_params.append(folder)
    author_sql = f"WHERE {' AND '.join(author_where)}" if author_where else ""
    author_rows = await db.query_all(
        f"""SELECT COALESCE(NULLIF(c.author_name, ''), '—') AS name, COUNT(*) AS count
            FROM favorites f LEFT JOIN contents c
              ON c.content_id = f.content_id AND c.platform = f.platform
            {author_sql} GROUP BY name ORDER BY count DESC""",
        tuple(author_params),
    )
    return {
        "total": (total_row or {}).get("n") or 0,
        "accounts": accounts_rows,
        "folders": folder_rows,
        "sources": source_rows,
        "authors": author_rows,
    }


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


async def clear_tasks() -> int:
    cur = await db.execute("DELETE FROM fetch_tasks")
    return cur.rowcount


# ---------- 标签聚合 ----------

async def list_tag_stats(limit: int = 100) -> list[dict]:
    """按标签聚合已打标内容数，倒序返回 [{tag, count}]。"""
    return await db.query_all(
        """SELECT je.value AS tag, COUNT(*) AS count
           FROM contents c, json_each(c.tags) je
           GROUP BY je.value
           ORDER BY count DESC, tag ASC
           LIMIT ?""",
        (limit,),
    )
