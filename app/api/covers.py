"""封面图统一读取入口与一键补齐。"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from app.database import db
from app.services import cover_worker

router = APIRouter(prefix="/api/v1/covers", tags=["covers"])


@router.get("/{platform}/{content_id}")
async def get_cover(platform: str, content_id: str):
    """前端封面统一走本接口：已本地化直接回文件，否则 307 跳远程原图并顺手入队本地化。"""
    row = await db.query_one(
        "SELECT cover_url, cover_file FROM contents WHERE platform = ? AND content_id = ?",
        (platform, content_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    if row.get("cover_file"):
        path = cover_worker.cover_path(platform, content_id)
        if path is not None:
            return FileResponse(path)
        # 文件丢失：清标记走远程兜底，等待补齐
        await db.execute(
            "UPDATE contents SET cover_file = 0 WHERE platform = ? AND content_id = ?",
            (platform, content_id),
        )
    url = str(row.get("cover_url") or "")
    if url.startswith("http"):
        cover_worker.enqueue(platform, content_id, url)
        return RedirectResponse(url, status_code=307)
    raise HTTPException(status_code=404, detail="该内容无封面")


@router.post("/backfill")
async def backfill_covers():
    """核对封面本地化状态入库，缺失的提交后台队列补齐。"""
    return await cover_worker.backfill()


@router.get("/status")
async def cover_status():
    """封面本地化进度（设置页轮询展示）。"""
    return await cover_worker.status()
