"""任务与数据查询 API（PRD 3.3）。"""
import asyncio
import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models import FavoriteItem, TaskOut
from app.services import data_store

router = APIRouter(prefix="/api/v1", tags=["queries"])

# 数据目录体积遍历结果缓存（profile 目录文件多，避免高频统计拖慢接口）
_dir_size_cache: tuple[float, int] = (0.0, 0)  # (计算时间戳, 字节数)
_DIR_SIZE_TTL = 300


def _dir_size(path) -> int:
    import os

    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _cached_dir_size(path) -> int:
    global _dir_size_cache
    now = time.monotonic()
    if now - _dir_size_cache[0] > _DIR_SIZE_TTL:
        _dir_size_cache = (now, _dir_size(path))
    return _dir_size_cache[1]


async def _count(sql: str, params: tuple = ()) -> int:
    row = await data_store.db.query_one(sql, params)
    return (row or {}).get("n") or 0


@router.get("/stats")
async def get_stats():
    """仪表盘统计：账号/收藏/任务/存储占用。"""
    from datetime import date

    from app import config

    today = date.today().isoformat()
    try:
        db_size = config.DB_PATH.stat().st_size
    except OSError:
        db_size = 0

    favorites_total, contents_total, today_new = await asyncio.gather(
        _count("SELECT COUNT(*) AS n FROM favorites"),
        _count("SELECT COUNT(*) AS n FROM contents"),
        _count("SELECT COUNT(*) AS n FROM favorites WHERE fetched_at >= ?", (today,)),
    )
    accounts_total, accounts_active, schedules_active = await asyncio.gather(
        _count("SELECT COUNT(*) AS n FROM accounts"),
        _count("SELECT COUNT(*) AS n FROM accounts WHERE status = 'active'"),
        _count("SELECT COUNT(*) AS n FROM schedules WHERE status = 'active'"),
    )
    tasks_running, tasks_today = await asyncio.gather(
        _count("SELECT COUNT(*) AS n FROM fetch_tasks WHERE status IN ('pending','running')"),
        _count("SELECT COUNT(*) AS n FROM fetch_tasks WHERE started_at >= ?", (today,)),
    )
    contents_tagged = await _count("SELECT COUNT(*) AS n FROM contents WHERE tags IS NOT NULL")
    return {
        "accounts_total": accounts_total,
        "accounts_active": accounts_active,
        "favorites_total": favorites_total,
        "contents_total": contents_total,
        "contents_tagged": contents_tagged,
        "today_new_favorites": today_new,
        "tasks_running": tasks_running,
        "tasks_today": tasks_today,
        "schedules_active": schedules_active,
        "db_size_bytes": db_size,
        "data_dir_size_bytes": await asyncio.to_thread(_cached_dir_size, config.DATA_DIR),
    }


@router.get("/tasks")
async def list_tasks(limit: int = Query(50, ge=1, le=500), account_id: str | None = None):
    return {"tasks": [TaskOut(**t).model_dump() for t in await data_store.list_tasks(limit, account_id)]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = await data_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
    return TaskOut(**task).model_dump()


@router.delete("/tasks")
async def clear_tasks():
    deleted = await data_store.clear_tasks()
    return {"deleted": deleted}


@router.get("/favorites/facets")
async def favorite_facets(account_id: str | None = None, folder: str | None = None):
    """数据浏览过滤面板候选：总数、各账号计数、收藏夹/作者候选（可按账号+收藏夹联动收敛）。"""
    return await data_store.favorite_facets(account_id, folder)


@router.get("/favorites")
async def list_favorites(
    account_id: str | None = None,
    platform: str | None = None,
    tag: str | None = None,
    folder: str | None = None,
    author: str | None = None,
    source: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    pub_start: str | None = None,
    pub_end: str | None = None,
    tags: str | None = Query(None, description="逗号分隔多标签，OR 匹配"),
    q: str | None = None,
    limit: int = Query(50, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    sort_by: str | None = Query(None, description="排序字段：collected（收藏时间）/ duration（时长），缺省按抓取时间"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    result = await data_store.list_favorites(
        account_id, platform, tag, folder, author, date_start, date_end, pub_start, pub_end,
        tag_list, q, source=source, limit=limit, offset=offset,
        sort_by=sort_by, sort_order=sort_order,
    )
    result["items"] = [FavoriteItem(**i).model_dump() for i in result["items"]]
    return result


class FavoriteRef(BaseModel):
    account_id: str
    platform: str
    content_id: str


class FavoritesBatchDelete(BaseModel):
    items: list[FavoriteRef] = Field(min_length=1)


@router.post("/favorites/batch-delete")
async def batch_delete_favorites(body: FavoritesBatchDelete):
    """批量删除收藏关系，并联动清理不再被引用的 contents 行。"""
    return await data_store.delete_favorites([i.model_dump() for i in body.items])


@router.delete("/favorites")
async def clear_favorites(account_id: str | None = Query(None, min_length=1)):
    """一键清空收藏关系（传 account_id 只清该账号，不传清空全部账号），联动清理孤儿 contents。"""
    return await data_store.clear_favorites(account_id)



@router.get("/tags")
async def list_tags(limit: int = Query(100, ge=1, le=500)):
    """AI 打标标签聚合统计（按引用内容数倒序）+ 分组定义（tag_groups 表 + 库中未匹配的「其他」组）。"""
    from app.services import tag_store

    stats = await data_store.list_tag_stats(limit)
    groups = await tag_store.list_groups()
    grouped = {t for g in groups for t in g["tags"]}
    others = sorted({s["tag"] for s in stats if s["tag"] not in grouped})
    if others:
        groups.append({"group": "其他", "tags": others})
    return {"tags": stats, "groups": groups}
