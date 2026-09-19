"""特别关注博主的共享资产：媒体 CDN 域白名单 / 请求 UA / 头像本地化。

follows API 层与各平台 adapter（同步作品回填头像）共用，避免 platforms → api 反向依赖。
"""

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

from app import config

logger = logging.getLogger("favapi.follows")

# 媒体域名白名单（视频 / 图片 / 音乐），媒体代理与头像下载共用：
# 抖音系 CDN + B 站系 CDN（i0/i1/i2.hdslb.com 头像封面、upos-sz-mirror*.bilivideo.com 视频直链）
# + 快手系 CDN（kwimgs 头像、yximgs 封面、kwaicdn/djvod.ndcimgs 视频直链，均仅 UA 即可访问）
# + 小红书系 CDN（sns-avatar/sns-webpic/sns-video*.xhscdn.com 头像/封面/直链，需站内 referer）
# + Threads CDN（scontent-*.cdninstagram.com 头像/封面/视频直链，仅 UA 即可访问）
MEDIA_HOST_SUFFIXES = (
    "douyinvod.com", "douyinpic.com", "douyinstatic.com", "douyin.com", "byteimg.com",
    "bytecdn.cn", "snssdk.com", "bytedance.com", "zjcdn.com", "volccdn.com",
    "ipdlab.com", "myqcloud.com",
    "hdslb.com", "bilivideo.com", "bilivideo.cn",
    "kwimgs.com", "yximgs.com", "kwaicdn.com", "ndcimgs.com",
    "xhscdn.com",
    "cdninstagram.com",
)
# 需要站内 referer 的平台 CDN（其余如 B 站直链不带 referer 最稳）
DOUYIN_REFERER = "https://www.douyin.com/"
_DOUYIN_REFERER_SUFFIXES = (
    "douyinvod.com", "douyinpic.com", "douyinstatic.com", "douyin.com",
    "zjcdn.com", "volccdn.com", "snssdk.com",
)
XHS_REFERER = "https://www.xiaohongshu.com/"
_XHS_REFERER_SUFFIXES = ("xhscdn.com",)

MEDIA_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# 博主头像本地化目录（data/follow_avatars/{sec_uid}.{ext}）：平台 CDN 头像带签名会过期，
# 添加博主时落盘一份，前端统一走 /follows/authors/{sec_uid}/avatar 读本地
AVATAR_DIR = config.DATA_DIR / "follow_avatars"
_AVATAR_EXTS = (".jpeg", ".jpg", ".png", ".webp")


def is_allowed_media_url(url: str) -> bool:
    """URL 是否在媒体 CDN 域白名单内（主机名后缀匹配）。

    http 也放行：部分平台接口仍下发 http 链接（如 B 站投稿封面 pic 字段），
    实际上游请求由 upgrade_media_url 统一升 https。
    """
    parsed = urlparse(url or "")
    host = parsed.hostname or ""
    return parsed.scheme in ("http", "https") and any(
        host == s or host.endswith("." + s) for s in MEDIA_HOST_SUFFIXES
    )


def upgrade_media_url(url: str) -> str:
    """白名单域的 http 链接升级 https（各平台 CDN 均支持，避免明文上游请求）。"""
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def media_referer(url: str) -> str:
    """按目标 CDN 域选 referer：抖音/小红书系需站内 referer，其余（B 站 CDN）直链不带最稳。"""
    host = urlparse(url or "").hostname or ""
    if any(host == s or host.endswith("." + s) for s in _XHS_REFERER_SUFFIXES):
        return XHS_REFERER
    return DOUYIN_REFERER if any(
        host == s or host.endswith("." + s) for s in _DOUYIN_REFERER_SUFFIXES
    ) else ""


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
    url = upgrade_media_url(url)
    try:
        headers = {"user-agent": MEDIA_UA}
        referer = media_referer(url)
        if referer:
            headers["referer"] = referer
        resp = curl_requests.get(
            url, headers=headers, impersonate="chrome", timeout=20,
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
