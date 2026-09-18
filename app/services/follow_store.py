"""特别关注博主的共享资产：抖音 CDN 域白名单 / 请求 UA / 头像本地化。

follows API 层与 douyin adapter（同步作品回填头像）共用，避免 platforms → api 反向依赖。
"""
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

from app import config

logger = logging.getLogger("favapi.follows")

# 抖音 CDN 媒体域名白名单（视频 / 图片 / 音乐），媒体代理与头像下载共用
MEDIA_HOST_SUFFIXES = (
    "douyinvod.com", "douyinpic.com", "douyinstatic.com", "douyin.com", "byteimg.com",
    "bytecdn.cn", "snssdk.com", "bytedance.com", "zjcdn.com", "volccdn.com",
    "ipdlab.com", "myqcloud.com",
)

MEDIA_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# 博主头像本地化目录（data/follow_avatars/{sec_uid}.{ext}）：抖音 CDN 头像带签名会过期，
# 添加博主时落盘一份，前端统一走 /follows/authors/{sec_uid}/avatar 读本地
AVATAR_DIR = config.DATA_DIR / "follow_avatars"
_AVATAR_EXTS = (".jpeg", ".jpg", ".png", ".webp")


def is_allowed_media_url(url: str) -> bool:
    """URL 是否在抖音 CDN 域白名单内（https 且主机名后缀匹配）。"""
    parsed = urlparse(url or "")
    host = parsed.hostname or ""
    return parsed.scheme == "https" and any(
        host == s or host.endswith("." + s) for s in MEDIA_HOST_SUFFIXES
    )


def avatar_local_path(sec_uid: str) -> Path | None:
    """已落盘的博主头像路径；sec_uid 字符白名单校验防路径穿越。"""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", sec_uid or ""):
        return None
    for ext in _AVATAR_EXTS:
        path = AVATAR_DIR / f"{sec_uid}{ext}"
        if path.is_file():
            return path
    return None


def download_avatar(sec_uid: str, url: str) -> Path | None:
    """下载博主头像落盘并返回路径（同步阻塞，异步侧 to_thread 调用）。

    域名白名单与媒体代理一致；成功前清理旧扩展名文件（content-type 可能变化）。
    """
    if not is_allowed_media_url(url):
        return None
    try:
        resp = curl_requests.get(
            url, headers={"user-agent": MEDIA_UA, "referer": "https://www.douyin.com/"},
            impersonate="chrome", timeout=20,
        )
        if resp.status_code != 200 or not resp.content:
            return None
        ctype = (resp.headers.get("content-type") or "").lower()
        ext = ".png" if "png" in ctype else ".webp" if "webp" in ctype else ".jpeg"
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        for old in AVATAR_DIR.glob(f"{sec_uid}.*"):
            old.unlink(missing_ok=True)
        path = AVATAR_DIR / f"{sec_uid}{ext}"
        path.write_bytes(resp.content)
        return path
    except Exception:
        logger.warning("博主头像下载失败：%s", sec_uid, exc_info=True)
        return None
