"""系统设置：Web 控制台本地偏好（头像、运行参数等）。"""
import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import DATA_DIR
from app.services.app_settings import load_settings, save_settings

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


class SettingsUpdate(BaseModel):
    profile_path: str | None = None
    headless: bool | None = None
    request_interval: float | None = Field(default=None, ge=1.0, le=5.0)
    request_timeout: int | None = Field(default=None, ge=1, le=600)
    download_dir: str | None = None          # 下载根目录，空 = 默认 data/downloads
    download_concurrency: int | None = Field(default=None, ge=1, le=3)


@router.get("")
async def get_settings():
    return load_settings()


@router.put("")
async def update_settings(body: SettingsUpdate):
    patch = body.model_dump(exclude_none=True)
    if "profile_path" in patch and not patch["profile_path"].strip():
        raise HTTPException(400, "存储路径不能为空")
    if "download_dir" in patch:
        patch["download_dir"] = patch["download_dir"].strip()
        if patch["download_dir"]:
            try:
                Path(patch["download_dir"]).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise HTTPException(400, f"下载目录不可用：{exc}")
    data = load_settings()
    data.update(patch)
    save_settings(data)
    logger.info("设置已更新: %s", patch)
    return data


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
