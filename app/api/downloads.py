"""下载队列 API：列表 / 入队 / 重试 / 删除（取消）。"""
from fastapi import APIRouter, HTTPException

from app.models import DownloadCreate, DownloadOut
from app.services import download_store, download_worker

router = APIRouter(prefix="/api/v1/downloads", tags=["downloads"])


async def _get_or_404(download_id: str) -> dict:
    row = await download_store.get_download(download_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"下载任务不存在：{download_id}")
    return row


@router.get("")
async def list_downloads():
    return {"downloads": [DownloadOut(**d).model_dump() for d in await download_store.list_downloads()]}


@router.post("", status_code=201)
async def create_download(body: DownloadCreate):
    try:
        row = await download_store.create_download(
            body.platform, body.content_id, body.title, body.url, body.downloader, body.account_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return DownloadOut(**row).model_dump()


@router.post("/{download_id}/retry", status_code=202)
async def retry_download(download_id: str):
    row = await _get_or_404(download_id)
    if row["status"] in ("pending", "running"):
        raise HTTPException(status_code=400, detail="任务仍在队列中，无需重试")
    await download_store.reset_download(download_id)
    return {"download_id": download_id, "status": "pending"}


@router.post("/{download_id}/pause", status_code=202)
async def pause_download(download_id: str):
    await _get_or_404(download_id)
    row = await download_store.pause_download(download_id)
    if row and row["status"] != "paused":
        raise HTTPException(status_code=400, detail=f"当前状态（{row['status']}）不支持暂停")
    return {"download_id": download_id, "status": "paused"}


@router.delete("/{download_id}")
async def delete_download(download_id: str):
    row = await _get_or_404(download_id)
    if row["status"] == "running":
        await download_worker.cancel(download_id)
    await download_store.delete_download(download_id)
    return {"deleted": download_id}
