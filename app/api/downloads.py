"""下载队列 API：列表 / 入队 / 重试 / 删除（取消）。"""
import subprocess
import sys
from pathlib import Path

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


@router.post("/{download_id}/reveal", status_code=200)
async def reveal_download(download_id: str):
    """在系统文件管理器中打开输出位置（Windows 资源管理器 / Finder / xdg-open）。

    output_path 为下载输出目录；目录被移动/删除时返回 404。
    """
    row = await _get_or_404(download_id)
    raw = str(row.get("output_path") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="该任务还没有输出位置（未开始或未完成）")
    target = Path(raw)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"输出位置不存在（可能已被移动或删除）：{raw}")
    folder = target if target.is_dir() else target.parent
    if sys.platform == "win32":
        # 文件用 /select 定位选中，目录直接打开
        args = ["explorer", "/select,", str(target)] if target.is_file() else ["explorer", str(folder)]
    elif sys.platform == "darwin":
        args = ["open", "-R", str(target)] if target.is_file() else ["open", str(folder)]
    else:
        args = ["xdg-open", str(folder)]
    subprocess.Popen(args)
    return {"revealed": True, "path": str(folder)}


@router.delete("/{download_id}")
async def delete_download(download_id: str):
    row = await _get_or_404(download_id)
    if row["status"] == "running":
        await download_worker.cancel(download_id)
    await download_store.delete_download(download_id)
    return {"deleted": download_id}
