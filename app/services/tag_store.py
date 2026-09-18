"""标签管理：分组持久化（首启物化内置体系）、标签删除、内容手动打标。"""
import json

from app.database import db
from app.utils import now_iso


# ---------- 分组 ----------

async def list_groups() -> list[dict]:
    rows = await db.query_all("SELECT group_name, tags FROM tag_groups ORDER BY rowid ASC")
    out = []
    for r in rows:
        try:
            tags = json.loads(r["tags"] or "[]")
        except (TypeError, json.JSONDecodeError):
            tags = []
        out.append({"group": r["group_name"], "tags": tags})
    return out


async def _group_exists(name: str) -> bool:
    return await db.query_one("SELECT 1 AS x FROM tag_groups WHERE group_name = ?", (name,)) is not None


async def create_group(name: str, tags: list[str] | None = None) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("分组名称不能为空")
    if await _group_exists(name):
        raise ValueError(f"分组已存在：{name}")
    cleaned = sorted({t.strip().strip("#").strip() for t in (tags or []) if t.strip().strip("#").strip()})
    row = {"group": name, "tags": cleaned}
    await db.execute(
        "INSERT INTO tag_groups (group_name, tags) VALUES (?, ?)",
        (name, json.dumps(cleaned, ensure_ascii=False)),
    )
    return row


async def rename_group(old: str, new: str) -> dict:
    new = new.strip()
    if not new:
        raise ValueError("分组名称不能为空")
    if new == old:
        row = await db.query_one("SELECT tags FROM tag_groups WHERE group_name = ?", (old,))
        return {"group": old, "tags": json.loads(row["tags"] or "[]") if row else []}
    if await _group_exists(new):
        raise ValueError(f"分组已存在：{new}")
    cur = await db.execute("UPDATE tag_groups SET group_name = ? WHERE group_name = ?", (new, old))
    if cur.rowcount == 0:
        raise ValueError(f"分组不存在：{old}")
    row = await db.query_one("SELECT tags FROM tag_groups WHERE group_name = ?", (new,))
    return {"group": new, "tags": json.loads(row["tags"] or "[]") if row else []}


# ---------- 标签删除 ----------

async def tag_usage(tag: str) -> int:
    row = await db.query_one(
        """SELECT COUNT(*) AS n FROM contents c
           WHERE EXISTS (SELECT 1 FROM json_each(c.tags) WHERE json_each.value = ?)""",
        (tag,),
    )
    return (row or {}).get("n") or 0


async def delete_tag(tag: str, delete_favorites: bool = False) -> dict:
    """从所有内容的 tags 中移除该标签；delete_favorites=true 时一并删除相关收藏关系，
    并联动清理不再被引用的 contents 行。"""
    rows = await db.query_all(
        """SELECT content_id, tags FROM contents c
           WHERE EXISTS (SELECT 1 FROM json_each(c.tags) WHERE json_each.value = ?)""",
        (tag,),
    )
    now = now_iso()
    for r in rows:
        try:
            tags = json.loads(r["tags"] or "[]")
        except (TypeError, json.JSONDecodeError):
            tags = []
        tags = [t for t in tags if t != tag]
        await db.execute(
            "UPDATE contents SET tags = ?, tagged_at = ? WHERE content_id = ?",
            (json.dumps(tags, ensure_ascii=False), now, r["content_id"]),
        )
    favorites_deleted = 0
    contents_deleted = 0
    if delete_favorites and rows:
        ids = [r["content_id"] for r in rows]
        ph = ", ".join("?" for _ in ids)
        cur = await db.execute(f"DELETE FROM favorites WHERE content_id IN ({ph})", tuple(ids))
        favorites_deleted = cur.rowcount
        # 联动清理不再被引用的 contents 行（延迟导入避免与 data_store 循环依赖）
        from app.services import data_store
        contents_deleted = await data_store.purge_orphan_contents(ids)
    # 分组中同步移除该标签
    for g in await list_groups():
        if tag in g["tags"]:
            remaining = [t for t in g["tags"] if t != tag]
            await db.execute(
                "UPDATE tag_groups SET tags = ? WHERE group_name = ?",
                (json.dumps(remaining, ensure_ascii=False), g["group"]),
            )
    return {"contents_updated": len(rows), "favorites_deleted": favorites_deleted, "contents_deleted": contents_deleted}


# ---------- 手动打标 ----------

async def set_content_tags(content_id: str, tags: list[str]) -> dict:
    row = await db.query_one("SELECT content_id FROM contents WHERE content_id = ?", (content_id,))
    if row is None:
        raise ValueError(f"内容不存在：{content_id}")
    cleaned: list[str] = []
    for t in tags:
        t = str(t).strip().strip("#").strip()
        if t and t not in cleaned:
            cleaned.append(t)
    cleaned = cleaned[:10]  # 单条内容标签上限
    await db.execute(
        "UPDATE contents SET tags = ?, tagged_at = ? WHERE content_id = ?",
        (json.dumps(cleaned, ensure_ascii=False), now_iso(), content_id),
    )
    return {"content_id": content_id, "tags": cleaned}
