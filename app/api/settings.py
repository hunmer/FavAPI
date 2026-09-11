"""系统设置：Web 控制台本地偏好（头像等）。"""
import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import DATA_DIR

logger = logging.getLogger("favapi.settings")

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

UPLOADS_DIR = DATA_DIR / "uploads"
ALLOWED_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_SIZE = 5 * 1024 * 1024


def _find_avatar() -> Path | None:
    if not UPLOADS_DIR.exists():
        return None
    return next(iter(sorted(UPLOADS_DIR.glob("avatar.*"))), None)


@router.post("/avatar")
async def upload_avatar(file: UploadFile):
    ext = ALLOWED_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, "仅支持 PNG / JPEG / WebP / GIF 图片")
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "图片不能超过 5MB")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    # 同一时刻只保留一张头像，旧的直接清掉（扩展名可能不同）
    for old in UPLOADS_DIR.glob("avatar.*"):
        old.unlink(missing_ok=True)
    (UPLOADS_DIR / f"avatar{ext}").write_bytes(data)
    logger.info("头像已更新: avatar%s (%.1f KB)", ext, len(data) / 1024)
    # 时间戳参数用于前端破缓存
    return {"url": f"/api/v1/settings/avatar?t={int(time.time())}"}


@router.get("/avatar")
async def get_avatar():
    path = _find_avatar()
    if not path:
        raise HTTPException(404, "尚未上传头像")
    return FileResponse(path)
