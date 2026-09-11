"""定时同步计划 API：CRUD + 立即触发。"""
from fastapi import APIRouter, HTTPException

from app.models import ScheduleCreate, ScheduleOut, ScheduleUpdate
from app.services import schedule_store
from app.services.scheduler import trigger_schedule

router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"])


async def _get_or_404(schedule_id: str) -> dict:
    row = await schedule_store.get_schedule(schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"计划不存在：{schedule_id}")
    return row


@router.get("")
async def list_schedules():
    return {"schedules": [ScheduleOut(**s).model_dump() for s in await schedule_store.list_schedules()]}


@router.post("", status_code=201)
async def create_schedule(body: ScheduleCreate):
    try:
        row = await schedule_store.create_schedule(
            body.account_id, body.cron_expr, body.title, body.action, body.params, body.status
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ScheduleOut(**row).model_dump()


@router.patch("/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleUpdate):
    await _get_or_404(schedule_id)
    fields = body.model_dump(exclude_none=True)
    if fields.get("status") not in (None, "active", "paused"):
        raise HTTPException(status_code=400, detail="status 仅支持 active / paused")
    try:
        row = await schedule_store.update_schedule(schedule_id, **fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ScheduleOut(**row).model_dump()


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str):
    await _get_or_404(schedule_id)
    await schedule_store.delete_schedule(schedule_id)
    return {"deleted": schedule_id}


@router.post("/{schedule_id}/trigger", status_code=202)
async def trigger(schedule_id: str):
    """立即触发一次（不影响原有 cron 周期）。"""
    await _get_or_404(schedule_id)
    try:
        return await trigger_schedule(schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
