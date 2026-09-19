"""特别关注博主的共享资产：媒体 CDN 域白名单 / 请求 UA / 头像本地化。

follows API 层与各平台 adapter（同步作品回填头像）共用，避免 platforms → api 反向依赖。
"""

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

from app import config
from app.utils import now_iso as _now_iso

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
    # YouTube 系 CDN（i.ytimg.com 封面、yt3.googleusercontent.com / yt3.ggpht.com
    # 头像、googlevideo.com 视频直链），仅 UA 即可访问但需代理出网
    "ytimg.com", "googleusercontent.com", "ggpht.com", "googlevideo.com", "gstatic.com",
    # TikTok 系 CDN（p16/p19*-sign*.tiktokcdn.com 头像封面、v16/v19-webapp-prime
    # 视频直链），需会话 cookie（见 media_cookies）且需代理出网
    "tiktokcdn.com", "tiktokcdn-us.com", "tiktok.com", "tiktokv.us", "byteoversea.com",
)
# 需要经代理出网的平台 CDN（YouTube / TikTok 系国际站；国内平台直连最快）
_PROXY_SUFFIXES = (
    "ytimg.com", "googleusercontent.com", "ggpht.com", "googlevideo.com", "gstatic.com",
    "tiktokcdn.com", "tiktokcdn-us.com", "tiktok.com", "tiktokv.us", "byteoversea.com",
)
# 需要站内 referer 的平台 CDN（其余如 B 站直链不带 referer 最稳）
DOUYIN_REFERER = "https://www.douyin.com/"
_DOUYIN_REFERER_SUFFIXES = (
    "douyinvod.com", "douyinpic.com", "douyinstatic.com", "douyin.com",
    "zjcdn.com", "volccdn.com", "snssdk.com",
)
XHS_REFERER = "https://www.xiaohongshu.com/"
_XHS_REFERER_SUFFIXES = ("xhscdn.com",)
TIKTOK_REFERER = "https://www.tiktok.com/"
_TIKTOK_SUFFIXES = (
    "tiktokcdn.com", "tiktokcdn-us.com", "tiktok.com", "tiktokv.us", "byteoversea.com",
)
# TikTok CDN 会话 cookie 缓存（tt_chain_token + ttwid；匿名访问首页即下发）
_TIKTOK_COOKIE_TTL_SEC = 3600
_tiktok_cookie_cache: dict = {"cookie": "", "ts": 0.0}
# 直链 URL → 获取会话 cookie 的登记表（TikTok 视频直链绑定获取会话，跨会话 403）：
# play_info 拉到直链时登记，媒体代理按 URL 精确注入；FIFO 上限防膨胀
_media_cookie_map: dict[str, str] = {}
_MEDIA_COOKIE_MAX = 256


def register_media_cookie(url: str, cookie: str) -> None:
    """登记某直链 URL 的专属会话 cookie（TikTok 视频直链绑定获取会话）。

    由 follows_play_info 类调用方在拿到直链后登记；直链 URL 自带 expire
    （约 2 天）且会话 cookie 短时效，超限 FIFO 淘汰最旧项即可。
    """
    if not url or not cookie:
        return
    if len(_media_cookie_map) >= _MEDIA_COOKIE_MAX:
        _media_cookie_map.pop(next(iter(_media_cookie_map)))
    _media_cookie_map[url] = cookie

MEDIA_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# 博主头像本地化目录（data/follow_avatars/{sec_uid}.{ext}）：平台 CDN 头像带签名会过期，
# 添加博主时落盘一份，前端统一走 /follows/authors/{sec_uid}/avatar 读本地
AVATAR_DIR = config.DATA_DIR / "follow_avatars"
_AVATAR_EXTS = (".jpeg", ".jpg", ".png", ".webp")

# 博主主页作品快照（data/follow_posts/{sec_uid}.json）：浏览抓到的作品分页实时
# 合并落盘；缩略图本地化到 data/follow_covers/{platform}/{content_id}.{ext}，
# 前端统一走 /follows/authors/{sec_uid}/posts/{content_id}/cover 读本地
FOLLOW_POSTS_DIR = config.DATA_DIR / "follow_posts"
FOLLOW_COVERS_DIR = config.DATA_DIR / "follow_covers"
# 快照里每条作品保留的字段（与 /follows/authors/{sec_uid}/posts 响应行一致，不含 read）
POSTS_ITEM_FIELDS = ("content_id", "title", "cover_url", "duration", "published_at", "url")


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
    """按目标 CDN 域选 referer：抖音/小红书/TikTok 系需站内 referer，其余（B 站 CDN）直链不带最稳。"""
    host = urlparse(url or "").hostname or ""
    if any(host == s or host.endswith("." + s) for s in _XHS_REFERER_SUFFIXES):
        return XHS_REFERER
    if any(host == s or host.endswith("." + s) for s in _TIKTOK_SUFFIXES):
        return TIKTOK_REFERER
    return DOUYIN_REFERER if any(
        host == s or host.endswith("." + s) for s in _DOUYIN_REFERER_SUFFIXES
    ) else ""


def _host_in(url: str, suffixes: tuple[str, ...]) -> bool:
    host = urlparse(url or "").hostname or ""
    return any(host == s or host.endswith("." + s) for s in suffixes)


def media_cookies(url: str) -> str:
    """按目标 CDN 域返回需注入的 cookie 头。

    TikTok 系 CDN：视频直链带 tk=tt_chain_token 校验（仅 UA 实测 403）且
    **绑定获取直链的会话**（跨会话 cookie 同样 403），优先查 register_media_cookie
    登记的 URL 级 cookie；未登记（如头像/封面图片）匿名访问 tiktok.com 首页
    换取 tt_chain_token/ttwid（TTL 缓存），换取失败返回空串。
    """
    registered = _media_cookie_map.get(url)
    if registered:
        return registered
    if not _host_in(url, _TIKTOK_SUFFIXES):
        return ""
    now = time.monotonic()
    if _tiktok_cookie_cache["cookie"] and now - _tiktok_cookie_cache["ts"] < _TIKTOK_COOKIE_TTL_SEC:
        return _tiktok_cookie_cache["cookie"]
    try:
        resp = curl_requests.get(
            TIKTOK_REFERER, headers={"user-agent": MEDIA_UA},
            impersonate="chrome", timeout=20, proxy=media_proxy(url),
        )
        cookie = "; ".join(f"{c.name}={c.value}" for c in resp.cookies.jar
                           if c.name in ("tt_chain_token", "ttwid"))
        if "tt_chain_token" in cookie:
            _tiktok_cookie_cache.update(cookie=cookie, ts=now)
            return cookie
        logger.warning("TikTok CDN cookie 换取失败（无 tt_chain_token）")
    except Exception:
        logger.warning("TikTok CDN cookie 换取异常", exc_info=True)
    return ""


def media_proxy(url: str) -> str | None:
    """按目标 CDN 域返回出网代理：YouTube 系走代理（国际站直连超时），其余直连。

    代理地址优先环境变量（HTTPS_PROXY 等），Windows 回退注册表桌面代理
    （与 tiktok/threads/youtube 平台 api_client 的 resolve_proxy 同一逻辑）。
    """
    host = urlparse(url or "").hostname or ""
    if not any(host == s or host.endswith("." + s) for s in _PROXY_SUFFIXES):
        return None
    import os
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(key):
            return os.environ[key]
    if os.name == "nt":
        try:
            import winreg
            reg = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            enabled = winreg.QueryValueEx(reg, "ProxyEnable")[0]
            server = winreg.QueryValueEx(reg, "ProxyServer")[0]
            winreg.CloseKey(reg)
            if enabled and server:
                parts = dict(p.split("=", 1) for p in str(server).split(";") if "=" in p)
                server = parts.get("https") or parts.get("http") or server
                if not str(server).startswith(("http://", "https://", "socks5://")):
                    server = "http://" + server
                return server
        except (OSError, ImportError, ValueError):
            pass
    return None


def avatar_local_path(sec_uid: str) -> Path | None:
    """已落盘的博主头像路径；sec_uid 字符白名单校验防路径穿越。"""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", sec_uid or ""):
        return None
    for ext in _AVATAR_EXTS:
        path = AVATAR_DIR / f"{sec_uid}{ext}"
        if path.is_file():
            return path
    return None


def _fetch_media(url: str) -> tuple[bytes, str] | None:
    """按 CDN 域规则（UA/referer/cookie/代理）拉一张图片 → (内容, 扩展名)；失败 None。"""
    if not is_allowed_media_url(url):
        return None
    url = upgrade_media_url(url)
    try:
        headers = {"user-agent": MEDIA_UA}
        referer = media_referer(url)
        if referer:
            headers["referer"] = referer
        cookies = media_cookies(url)  # TikTok 系 CDN 需会话 cookie
        if cookies:
            headers["cookie"] = cookies
        resp = curl_requests.get(
            url, headers=headers, impersonate="chrome", timeout=20,
            proxy=media_proxy(url),
        )
        if resp.status_code != 200 or not resp.content:
            return None
        ctype = (resp.headers.get("content-type") or "").lower()
        ext = ".png" if "png" in ctype else ".webp" if "webp" in ctype else ".jpeg"
        return resp.content, ext
    except Exception:
        logger.warning("媒体图片下载失败：%s", url, exc_info=True)
        return None


def download_avatar(sec_uid: str, url: str) -> Path | None:
    """下载博主头像落盘并返回路径（同步阻塞，异步侧 to_thread 调用）。

    域名白名单与媒体代理一致；成功前清理旧扩展名文件（content-type 可能变化）。
    """
    media = _fetch_media(url)
    if media is None:
        return None
    content, ext = media
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    for old in AVATAR_DIR.glob(f"{sec_uid}.*"):
        old.unlink(missing_ok=True)
    path = AVATAR_DIR / f"{sec_uid}{ext}"
    path.write_bytes(content)
    return path


# ---------- 博主主页作品快照与缩略图 ----------

def _safe_id(value: str) -> str:
    return re.sub(r"[^\w.-]+", "_", str(value).strip())[:120] or "_"


def posts_json_path(sec_uid: str) -> Path | None:
    """博主作品快照 JSON 路径；sec_uid 字符白名单校验防路径穿越。"""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", sec_uid or ""):
        return None
    return FOLLOW_POSTS_DIR / f"{sec_uid}.json"


def load_posts(sec_uid: str) -> dict:
    """读取博主作品快照（缺失/损坏回空结构 {items: []}）。"""
    path = posts_json_path(sec_uid)
    if path is None or not path.is_file():
        return {"items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data.get("items"), list) else {"items": []}
    except (OSError, json.JSONDecodeError):
        logger.warning("博主作品快照读取失败：%s", sec_uid, exc_info=True)
        return {"items": []}


def save_posts_page(platform: str, sec_uid: str, items: list[dict], first_page: bool) -> None:
    """把浏览到的一页作品合并进博主快照 JSON（同步阻塞，异步侧 to_thread 调用）。

    按 content_id 去重更新（刷新签名链接等）；新作品首页抓到插最前（作者新发），
    翻页抓到追加末尾（更早历史），保持整体新→旧顺序。临时文件 + replace 原子写。
    """
    if not items:
        return
    path = posts_json_path(sec_uid)
    if path is None:
        return
    data = load_posts(sec_uid)
    merged: dict[str, dict] = {}
    for it in data.get("items", []):
        if it.get("content_id"):
            merged[it["content_id"]] = it
    new_ids: list[str] = []
    for it in items:
        cid = str(it.get("content_id") or "")
        if not cid:
            continue
        row = {k: it.get(k) for k in POSTS_ITEM_FIELDS}
        if cid in merged:
            merged[cid].update(row)
        else:
            merged[cid] = row
            new_ids.append(cid)
    new_set = set(new_ids)
    old_rows = [r for cid, r in merged.items() if cid not in new_set]
    new_rows = [merged[cid] for cid in new_ids]
    ordered = new_rows + old_rows if first_page else old_rows + new_rows
    payload = {
        "sec_uid": sec_uid, "platform": platform, "updated_at": _now_iso(), "items": ordered,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def follow_cover_path(platform: str, content_id: str) -> Path | None:
    """已落盘的作品缩略图路径（按 content_id 前缀匹配任意扩展名）；无则 None。"""
    folder = FOLLOW_COVERS_DIR / _safe_id(platform)
    if not folder.exists():
        return None
    return next(iter(sorted(folder.glob(f"{_safe_id(content_id)}.*"))), None)


def download_follow_cover(platform: str, content_id: str, url: str) -> Path | None:
    """下载作品缩略图落盘并返回路径（同步阻塞，异步侧 to_thread 调用）。"""
    media = _fetch_media(url)
    if media is None:
        return None
    content, ext = media
    folder = FOLLOW_COVERS_DIR / _safe_id(platform)
    folder.mkdir(parents=True, exist_ok=True)
    base = _safe_id(content_id)
    for old in folder.glob(f"{base}.*"):
        old.unlink(missing_ok=True)
    path = folder / f"{base}{ext}"
    path.write_bytes(content)
    return path


def delete_author_assets(sec_uid: str) -> int:
    """删除博主时清理其作品快照 JSON 与已本地化的缩略图；返回删除的文件数。"""
    data = load_posts(sec_uid)
    platform = str(data.get("platform") or "")
    deleted = 0
    for it in data.get("items", []):
        cover = follow_cover_path(platform, str(it.get("content_id") or ""))
        if cover is not None:
            try:
                cover.unlink()
                deleted += 1
            except OSError:
                pass  # 文件被占用等，残留无害
    path = posts_json_path(sec_uid)
    if path is not None:
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            pass
    return deleted
