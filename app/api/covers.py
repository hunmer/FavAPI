"""封面图统一读取入口与一键补齐。"""
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app.database import db
from app.services import cover_worker

router = APIRouter(prefix="/api/v1/covers", tags=["covers"])

# 手动上传封面：MIME → 落盘扩展名（与下载本地化的文件命名规则一致）
_COVER_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_COVER_MAX_BYTES = 10 * 1024 * 1024


@router.post("/{platform}/{content_id}")
async def upload_cover(platform: str, content_id: str, file: UploadFile = File(...)):
    """手动上传封面（手动录入条目等）：写入封面缓存目录并标记已本地化，覆盖旧封面。"""
    row = await db.query_one(
        "SELECT 1 AS x FROM contents WHERE platform = ? AND content_id = ?",
        (platform, content_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    ext = _COVER_EXT_BY_TYPE.get((file.content_type or "").lower())
    if ext is None:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的图片格式：{file.content_type or '未知'}（支持 jpg/png/webp/gif）",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="封面文件为空")
    if len(data) > _COVER_MAX_BYTES:
        raise HTTPException(status_code=422, detail="封面超过 10MB 上限")
    cover_worker.save_upload(platform, content_id, data, ext)
    await db.execute(
        "UPDATE contents SET cover_file = 1 WHERE platform = ? AND content_id = ?",
        (platform, content_id),
    )
    return {"ok": True}


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
