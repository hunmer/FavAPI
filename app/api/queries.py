"""任务与数据查询 API（PRD 3.3）。"""
from fastapi import APIRouter, HTTPException, Query

from app.models import FavoriteItem, TaskOut
from app.services import data_store

router = APIRouter(prefix="/api/v1", tags=["queries"])


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
