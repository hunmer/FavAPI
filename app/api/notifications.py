"""通知中心 API：列表（含未读数）、全部已读、清空。"""
from fastapi import APIRouter, Query

from app.models import NotificationOut
from app.services import notification_store

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(limit: int = Query(50, ge=1, le=200)):
    return {
        "notifications": [
            NotificationOut(**n).model_dump() for n in await notification_store.list_notifications(limit)
        ],
        "unread": await notification_store.unread_count(),
    }


@router.post("/read-all")
async def read_all():
    return {"updated": await notification_store.mark_all_read()}


@router.delete("")
async def clear_notifications():
    return {"deleted": await notification_store.clear_notifications()}
