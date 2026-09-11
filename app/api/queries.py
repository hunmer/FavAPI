"""任务与数据查询 API（PRD 3.3）。"""
import asyncio
import time

from fastapi import APIRouter, HTTPException, Query

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
    return {
        "accounts_total": accounts_total,
        "accounts_active": accounts_active,
        "favorites_total": favorites_total,
        "contents_total": contents_total,
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


@router.get("/favorites")
async def list_favorites(
    account_id: str | None = None,
    platform: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    result = await data_store.list_favorites(account_id, platform, limit, offset)
    result["items"] = [FavoriteItem(**i).model_dump() for i in result["items"]]
    return result
