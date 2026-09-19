"""YouTube InnerTube API 直连客户端（订阅列表 / 频道视频列表，follows 体系用）。

2026-09 用 JS Reverse MCP 抓包验证的协议要点（全部实测）：
- 接口统一为 POST /youtubei/v1/browse（JSON body），无独立签名，靠
  curl_cffi impersonate="chrome" 的 TLS 指纹 + 登录 cookie 即可直连。
- **context 只需最小字段集** {clientName: WEB, clientVersion, hl, gl}，
  浏览器请求里的一大堆 visitorData/adSignalsInfo 均可省。
- **订阅列表**（私有数据）：browseId="FEchannels" 必须带 SAPISIDHASH
  authorization 头（sha1("{ts} {SAPISID} https://www.youtube.com")，SAPISID
  取自 cookie），只带 cookie 不带该头 → 服务端按未登录处理，返回空 contents
  （responseContext.mainAppWebResponseContext.loggedOut=true 可作登录失效判定）。
- **频道视频列表**：browseId="UC..." + params=Videos tab 常量，匿名可用；
  响应 selected tab 即 Videos（richGridRenderer）。
- **翻页**：continuation token 请求（body 换成 {"continuation": token}），
  响应条目在 onResponseReceivedActions[].appendContinuationItemsAction.
  continuationItems[]，末尾 continuationItemRenderer 带下一页 token。
  注意字段名是 continuationCommand.**token**（不是 continuation）。
- API key / clientVersion 从首页 HTML 的 ytcfg 提取（公开，匿名可取），
  模块级缓存一次。
- 2026 前端渲染体系：视频条目为 lockupViewModel（不再是 videoRenderer），
  频道条目为 channelRenderer；channelRenderer 的字段语义有历史反转 ——
  新版 videoCountText=订阅数文本、subscriberCountText=handle("@xxx")，
  解析时按文本形态兼容两种。
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta

from curl_cffi import requests

from app.services import browser
from . import constants
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.youtube.api")

_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.youtube.com",
    "referer": "https://www.youtube.com/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-origin": "https://www.youtube.com",
    "x-youtube-client-name": "1",  # WEB（InnerTube clientName 的数字编码）
}

# 首页 ytcfg 提取（模块级缓存，首次请求时填充）
_ytcfg: dict = {}


def resolve_proxy() -> str | None:
    """代理地址：优先环境变量；Windows 桌面代理回退注册表 Internet Settings。

    YouTube 为国际站，直连请求与 profile 浏览器会话均需代理；
    与 tiktok/threads 平台的 resolve_proxy 同一逻辑。
    """
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(key):
            return os.environ[key]
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            server = winreg.QueryValueEx(key, "ProxyServer")[0]
            winreg.CloseKey(key)
            if enabled and server:
                parts = dict(p.split("=", 1) for p in str(server).split(";") if "=" in p)
                server = parts.get("https") or parts.get("http") or server
                if not str(server).startswith(("http://", "https://", "socks5://")):
                    server = "http://" + server
                return server
        except (OSError, ImportError, ValueError):
            pass
    return None


def _site_cookies(cookies: list[dict]) -> list[dict]:
    """筛选会随请求发往 www.youtube.com 的 cookie（复刻浏览器 domain 匹配）。

    profile 里同时存有 .google.com 与 .youtube.com 两域的同名 cookie
    （SAPISID/SID/HSID 等），全部拼入会同名并存导致服务端按未登录处理
    （browse 响应 loggedOut=true，2026-09 实测），必须按域过滤。
    """
    matched = []
    for c in cookies:
        domain = str(c.get("domain") or "").lstrip(".")
        if domain in ("youtube.com", "www.youtube.com") or (
                domain.endswith(".youtube.com") and "www.youtube.com".endswith(domain)):
            matched.append(c)
    return matched


async def profile_cookie_header(profile_path: str) -> str:
    """从持久化浏览器 profile 读取 cookies 拼 cookie 头。

    无登录 cookie 时抛 LoginExpiredError（与浏览器模式同一判定）。
    统一走 browser.session()：channel/并发上限/同 profile 串行锁一处维护。
    """
    async with browser.session(profile_path, headless=True, proxy=resolve_proxy()) as ctx:
        cookies = await ctx.cookies()
    cookies = _site_cookies(cookies)
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("YouTube 登录态缺失（profile 无 SID/SAPISID），请重新登录")
    return header


def _cookie_value(cookie_header: str, name: str) -> str:
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def _sapisidhash(cookie_header: str) -> str:
    """登录接口的 authorization 头：SAPISIDHASH {ts}_{sha1(ts SAPISID origin)}。

    SAPISID 缺失时按 AUTH_COOKIE_KEYS 依次取 3P/1P 变体（同一算法）；
    全部缺失视为登录态不完整。
    """
    sapisid = ""
    for name in constants.AUTH_COOKIE_KEYS:
        sapisid = _cookie_value(cookie_header, name)
        if sapisid:
            break
    if not sapisid:
        raise LoginExpiredError("YouTube cookie 中无 SAPISID（无法生成 authorization），请重新登录")
    ts = int(time.time())
    digest = hashlib.sha1(
        f"{ts} {sapisid} https://www.youtube.com".encode()
    ).hexdigest()
    return f"SAPISIDHASH {ts}_{digest}"


def _ensure_ytcfg(session: requests.Session) -> dict:
    """从首页 HTML 提取 INNERTUBE_API_KEY / INNERTUBE_CLIENT_VERSION（公开常量）。

    失败时退公开默认值（WEB key 多年稳定）；提取结果模块级缓存。
    """
    if _ytcfg.get("key") and _ytcfg.get("version"):
        return _ytcfg
    try:
        html = session.get(constants.HOME_URL, headers=_HEADERS,
                           timeout=20, proxy=resolve_proxy()).text
        key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
        version = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', html)
        if key and version:
            _ytcfg.update(key=key.group(1), version=version.group(1))
    except Exception:
        logger.warning("提取 ytcfg 失败，使用默认 InnerTube 参数", exc_info=True)
    _ytcfg.setdefault("key", "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8")  # WEB 公开 key
    _ytcfg.setdefault("version", "2.20240702.01.00")
    return _ytcfg


def _client_context(session: requests.Session) -> dict:
    """InnerTube 请求的 context.client 最小字段集。"""
    cfg = _ensure_ytcfg(session)
    return {"clientName": "WEB", "clientVersion": cfg["version"], "hl": "en", "gl": "US"}


def _browse(session: requests.Session, cookie_header: str, payload: dict,
            require_auth: bool = False) -> dict:
    """POST /youtubei/v1/browse 统一入口（同步阻塞）。

    require_auth=True 时带 SAPISIDHASH 头（私有 feed 如订阅列表）；
    带登录 cookie 但响应 loggedOut=true → LoginExpiredError。
    """
    headers = dict(_HEADERS)
    headers["x-youtube-client-version"] = _client_context(session)["clientVersion"]
    if require_auth:
        headers["authorization"] = _sapisidhash(cookie_header)
    if cookie_header:
        headers["cookie"] = cookie_header
    response = session.post(
        f"{constants.INNERTUBE_BROWSE_API}?key={_ytcfg['key']}&prettyPrint=false",
        headers=headers, json=payload, timeout=20, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    payload = response.json()
    if require_auth and (
        (payload.get("responseContext") or {}).get("mainAppWebResponseContext", {})
        .get("loggedOut")
    ):
        raise LoginExpiredError("YouTube 登录态失效（browse 响应 loggedOut），请重新登录")
    return payload


def _find_all(node, key: str) -> list:
    """递归收集 JSON 树中所有 dict[key] 的值（YouTube 渲染树结构多变，按 key 定位最稳）。"""
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                found.append(v)
            found.extend(_find_all(v, key))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_all(item, key))
    return found


def _continuation_token(node) -> str:
    """单个 continuationItemRenderer → token（字段名 token/continuation 两种形态兼容）。"""
    command = ((node or {}).get("continuationEndpoint") or {}).get("continuationCommand") or {}
    return str(command.get("token") or command.get("continuation") or "")


def _grid_continuation_token(payload: dict) -> str:
    """响应中与列表条目同级的 continuation token（空串 = 无更多页）。

    必须优先取 selected tab richGrid 内的 token：整个响应树里存在多个
    continuationItemRenderer（sidebar/其他模块也带），取错会路由到
    channel.featured 返回空（2026-09 实测），因此精确路径优先、树遍历退化取首个。
    """
    tabs = (((payload.get("contents") or {}).get("twoColumnBrowseResultsRenderer") or {})
            .get("tabs") or [])
    for tab in tabs:
        renderer = tab.get("tabRenderer") or {}
        grid = (renderer.get("content") or {}).get("richGridRenderer") or {}
        for item in grid.get("contents") or []:
            token = _continuation_token(item.get("continuationItemRenderer"))
            if token:
                return token
        for section in ((renderer.get("content") or {}).get("sectionListRenderer") or {}).get("contents") or []:
            for item in (section.get("itemSectionRenderer") or {}).get("contents") or []:
                token = _continuation_token(item.get("continuationItemRenderer"))
                if token:
                    return token
    for node in _find_all(payload, "continuationItemRenderer"):
        token = _continuation_token(node)
        if token:
            return token
    return ""


def _text(node) -> str:
    """裸字符串 / simpleText / runs 拼接 / content 四种文本形态统一提取。"""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return str(node.get("simpleText") or "")
    if "content" in node:
        return str(node.get("content") or "")
    return "".join(str(r.get("text") or "") for r in node.get("runs") or [])


def _parse_count(text: str) -> int | None:
    """"4.3K subscribers" / "1.5K views" → 数字；无数字返回 None。"""
    m = re.search(r"([\d.,]+)\s*([KMB])?", str(text or ""), re.I)
    if not m:
        return None
    try:
        number = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (m.group(2) or "").upper()
    return int(number * {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(unit, 1))


def _length_seconds(length: str) -> int | None:
    """"H:MM:SS" / "MM:SS" → 秒。"""
    parts = str(length or "").split(":")
    if not parts or not all(p.strip().isdigit() for p in parts):
        return None
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + int(p)
    return seconds


def _published_at(text: str) -> str | None:
    """相对发布时间 "1 year ago" → 近似 ISO 日期（YouTube 不下发精确时间戳）。"""
    m = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s? ago", str(text or ""), re.I)
    if not m:
        return None
    unit = {"second": timedelta(seconds=1), "minute": timedelta(minutes=1),
            "hour": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(weeks=1),
            "month": timedelta(days=30), "year": timedelta(days=365)}[m.group(2).lower()]
    return (datetime.now() - int(m.group(1)) * unit).isoformat(timespec="seconds")


def _avatar_url(thumbnails: list) -> str:
    """头像/封面取最宽一档；YouTube 下发 //host/... 形态时补 https:。"""
    best = ""
    best_width = -1
    for t in thumbnails or []:
        width = int(t.get("width") or 0)
        if width > best_width:
            best, best_width = str(t.get("url") or ""), width
    if best.startswith("//"):
        best = "https:" + best
    return best


def _parse_channel(renderer: dict) -> dict | None:
    """channelRenderer → 订阅条目（统一 followings 结构，adapter 层零转换）。

    新版字段语义：videoCountText=订阅数文本、subscriberCountText=handle；
    旧版相反（subscriberCountText=订阅数）。按文本形态兼容。
    """
    channel_id = str(renderer.get("channelId") or "")
    if not channel_id:
        return None
    handle = ""
    subscriber_text = ""
    count_text = _text(renderer.get("videoCountText"))
    sub_text = _text(renderer.get("subscriberCountText"))
    if sub_text.startswith("@"):
        handle, subscriber_text = sub_text, count_text
    elif "subscriber" in sub_text.lower() or "订阅" in sub_text:
        subscriber_text = sub_text
    canonical = ((((renderer.get("navigationEndpoint") or {}).get("browseEndpoint") or {})
                  .get("canonicalBaseUrl")) or "").strip()
    if canonical.startswith("/@"):
        handle = handle or canonical[1:]
    return {
        "sec_uid": channel_id,
        "uid": channel_id,
        "unique_id": handle.lstrip("@"),
        "nickname": _text(renderer.get("title")) or None,
        "signature": _text(renderer.get("descriptionSnippet")) or None,
        "avatar_url": _avatar_url(renderer.get("thumbnail", {}).get("thumbnails")) or None,
        "follower_count": _parse_count(subscriber_text),
        "aweme_count": None,
        "is_top": False,
        "subscriber_text": subscriber_text or None,
    }


def _parse_video_lockup(renderer: dict, channel_id: str, author_name: str | None) -> dict | None:
    """lockupViewModel（2026 前端视频卡）→ 通用 content 行。"""
    video_id = str(renderer.get("contentId") or "")
    if not video_id:
        return None
    metadata = ((renderer.get("metadata") or {}).get("lockupMetadataViewModel") or {})
    thumbnail_vm = ((renderer.get("contentImage") or {}).get("thumbnailViewModel") or {})
    parts = []
    for row in (((metadata.get("metadata") or {}).get("contentMetadataViewModel") or {})
                .get("metadataRows") or []):
        parts.extend(_text(p.get("text")) for p in row.get("metadataParts") or [])
    view_text = next((p for p in parts if "view" in p.lower() or "观看" in p), "")
    published_text = next((p for p in parts if "ago" in p.lower() or "前" in p), "")
    duration_text = ""
    for overlay in thumbnail_vm.get("overlays") or []:
        for badge in (overlay.get("thumbnailBottomOverlayViewModel") or {}).get("badges") or []:
            duration_text = duration_text or _text(
                (badge.get("thumbnailBadgeViewModel") or {}).get("text"))
    return {
        "content_id": video_id,
        "title": _text(metadata.get("title")) or None,
        "description": None,
        "author_id": channel_id,
        "author_name": author_name,
        "cover_url": _avatar_url((thumbnail_vm.get("image") or {}).get("sources")) or None,
        "duration": _length_seconds(duration_text),
        "statistics": json.dumps(
            {"play": _parse_count(view_text), "view_text": view_text or None},
            ensure_ascii=False),
        "raw_data": json.dumps(
            {"videoId": video_id, "title": _text(metadata.get("title")),
             "durationText": duration_text, "viewText": view_text,
             "publishedText": published_text},
            ensure_ascii=False),
        "collected_at": _published_at(published_text),
    }


def _channel_author(payload: dict) -> str | None:
    """browse 频道响应 header 里的频道名（视频条目自身不带作者，统一回填）。"""
    header = payload.get("header") or {}
    for key in ("pageHeaderRenderer", "c4TabbedHeaderRenderer"):
        node = header.get(key)
        if not node:
            continue
        title = node.get("pageTitle") or _text(node.get("title"))
        if title:
            return title
    return None


# ---------- 当前账号（follows_self_uid 用） ----------

def fetch_self_channel_id(cookie_header: str) -> str:
    """登录账号的频道 ID（UC 开头）：guide 响应 You 分区的 Your channel 条目。

    各 browse/player 响应均不下发当前账号 UC，guide（左侧导航）是唯一入口；
    提取失败返回空串（follows API 层转 400）。
    """
    session = requests.Session(impersonate="chrome")
    try:
        response = session.post(
            f"https://www.youtube.com/youtubei/v1/guide?key={_ensure_ytcfg(session)['key']}&prettyPrint=false",
            headers={**_HEADERS, "authorization": _sapisidhash(cookie_header),
                     "cookie": cookie_header},
            json={"context": {"client": _client_context(session)}},
            timeout=20, proxy=resolve_proxy(),
        )
        response.raise_for_status()
        guide = response.json()
        for entry in _find_all(guide, "guideEntryRenderer"):
            title = _text(entry.get("formattedTitle") or entry.get("title")).lower()
            if "your channel" not in title and "你的频道" not in title:
                continue
            browse_id = str((((entry.get("navigationEndpoint") or {}).get("browseEndpoint")
                              or {}).get("browseId")) or "")
            if browse_id.startswith("UC"):
                return browse_id
        return ""
    finally:
        session.close()


# ---------- 视频播放信息（follows_play_info 用） ----------

def fetch_video_play_info(cookie_header: str, video_id: str) -> dict:
    """单视频播放信息（POST player，WEB client + 登录态，同步阻塞）。

    返回 PlayerModal 统一结构。注意：YouTube 的 WEB client 直链（googlevideo）
    带 PO token 深度绑定生成会话（2026 实测：同机同代理裸 UA 一律 403），
    不可独立访问 —— video_urls 留空，改下发官方 embed 的 iframe_url，
    前端用 <iframe> 播放（发布时间/统计/作者取自 videoDetails + microformat）。
    """
    video_id = str(video_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
        raise ValueError("YouTube 作品 ID 格式不合法（应为 11 位视频编号）")
    session = requests.Session(impersonate="chrome")
    try:
        response = session.post(
            f"https://www.youtube.com/youtubei/v1/player?key={_ensure_ytcfg(session)['key']}&prettyPrint=false",
            headers={**_HEADERS, "authorization": _sapisidhash(cookie_header),
                     "cookie": cookie_header},
            json={"context": {"client": _client_context(session)}, "videoId": video_id,
                  "contentCheckOk": True, "racyCheckOk": True},
            timeout=20, proxy=resolve_proxy(),
        )
        response.raise_for_status()
        payload = response.json()
        playability = (payload.get("playabilityStatus") or {}).get("status")
        if playability != "OK":
            reason = (payload.get("playabilityStatus") or {}).get("reason") or playability
            raise RuntimeError(f"YouTube player 返回不可播放状态：{reason}")
        details = payload.get("videoDetails") or {}
        microformat = (payload.get("microformat") or {}).get("playerMicroformatRenderer") or {}
        publish_date = str(microformat.get("publishDate") or "")
        return {
            "aweme_id": details.get("videoId") or video_id,
            "desc": details.get("title"),
            "create_time": datetime.fromisoformat(publish_date).timestamp()
            if publish_date else None,
            "aweme_type": 0,
            "duration": _as_int_or_none(details.get("lengthSeconds")),
            "statistics": {"play": _as_int_or_none(details.get("viewCount"))},
            "author": {"nickname": details.get("author"),
                       "sec_uid": details.get("channelId")},
            "video_urls": [],
            # 必须用主站域 embed（同域带浏览器 YouTube 登录 cookie）：
            # nocookie 域匿名会话会触发 "Sign in to confirm you're not a
            # bot" 反机器人验证（2026-09 实测）
            "iframe_url": f"https://www.youtube.com/embed/{video_id}?autoplay=1&rel=0",
            "images": [],
            "music_url": None,
        }
    finally:
        session.close()


def _as_int_or_none(value) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


# ---------- 订阅列表（follows 体系：关注列表拉取） ----------

def fetch_subscriptions_page(cookie_header: str, continuation: str = "",
                              session: requests.Session | None = None) -> dict:
    """拉取一页订阅列表（POST browse FEchannels，同步阻塞，异步侧用 asyncio.to_thread）。

    continuation 为空 = 首页。返回 {followings, continuation(下一页 token，空=无更多)}。
    """
    own_session = session is None
    session = session or requests.Session(impersonate="chrome")
    try:
        payload = {"context": {"client": _client_context(session)}}
        if continuation:
            payload["continuation"] = continuation
        else:
            payload["browseId"] = constants.SUBSCRIPTIONS_BROWSE_ID
        data = _browse(session, cookie_header, payload, require_auth=True)
        followings = [entry for entry in (
            _parse_channel(r) for r in _find_all(data, "channelRenderer")
        ) if entry]
        # 去重（翻页重叠场景防御）
        seen = set()
        unique = []
        for entry in followings:
            if entry["sec_uid"] not in seen:
                seen.add(entry["sec_uid"])
                unique.append(entry)
        return {"followings": unique, "continuation": _grid_continuation_token(data)}
    finally:
        if own_session:
            session.close()


async def fetch_subscriptions(cookie_header: str, count: int = 0, on_batch=None):
    """翻页拉取订阅列表，直到取满 count（0=全部）或无 continuation。

    返回 (全部 followings, has_more)；on_batch({"page", "followings"}) 逐页回调。
    """
    session = requests.Session(impersonate="chrome")
    collected: list[dict] = []
    continuation = ""
    page = 0
    try:
        while True:
            batch = await asyncio.to_thread(
                fetch_subscriptions_page, cookie_header, continuation, session)
            page += 1
            collected.extend(batch["followings"])
            logger.info("subscriptions 第 %d 页：%d 条，累计 %d，has_more=%s",
                        page, len(batch["followings"]), len(collected),
                        bool(batch["continuation"]))
            if on_batch and batch["followings"]:
                await on_batch({"page": page, "followings": batch["followings"]})
            if not batch["continuation"] or not batch["followings"]:
                return collected, False
            if count and len(collected) >= count:
                return collected, True
            continuation = batch["continuation"]
            await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)
    finally:
        session.close()


# ---------- 频道视频列表（follows 体系：博主主页作品） ----------

def fetch_channel_videos_page(cookie_header: str, channel_id: str, continuation: str = "",
                              session: requests.Session | None = None) -> dict:
    """拉取一页频道 Videos tab（POST browse UC..，同步阻塞）。

    continuation 为空 = 首页（browseId + Videos tab params，匿名可用）。
    返回 {items(通用 content 行), continuation(下一页 token，空=无更多), author_name}。
    """
    own_session = session is None
    session = session or requests.Session(impersonate="chrome")
    try:
        payload = {"context": {"client": _client_context(session)}}
        if continuation:
            payload["continuation"] = continuation
        else:
            payload["browseId"] = str(channel_id or "").strip()
            payload["params"] = constants.VIDEOS_TAB_PARAMS
        data = _browse(session, cookie_header, payload)
        author_name = _channel_author(data)
        items = [item for item in (
            _parse_video_lockup(r, str(channel_id), author_name)
            for r in _find_all(data, "lockupViewModel")
        ) if item]
        return {"items": items, "continuation": _grid_continuation_token(data),
                "author_name": author_name}
    finally:
        if own_session:
            session.close()


async def fetch_channel_videos(cookie_header: str, channel_id: str, count: int = 0,
                               on_batch=None):
    """翻页拉取频道视频列表，直到取满 count（0=全部）或无 continuation。

    返回 (全部 items, has_more)；on_batch({"page", "items"}) 逐页回调。
    """
    session = requests.Session(impersonate="chrome")
    collected: list[dict] = []
    continuation = ""
    page = 0
    try:
        while True:
            batch = await asyncio.to_thread(
                fetch_channel_videos_page, cookie_header, channel_id, continuation, session)
            page += 1
            collected.extend(batch["items"])
            logger.info("channel videos 第 %d 页：%d 条，累计 %d，has_more=%s",
                        page, len(batch["items"]), len(collected),
                        bool(batch["continuation"]))
            if on_batch and batch["items"]:
                await on_batch({"page": page, "items": batch["items"]})
            if not batch["continuation"] or not batch["items"]:
                return collected, False
            if count and len(collected) >= count:
                return collected, True
            continuation = batch["continuation"]
            await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)
    finally:
        session.close()
