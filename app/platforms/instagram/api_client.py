"""Instagram API 直连客户端（收藏抓取 + 特别关注体系，2026-09 接入）。

Instagram Web 混用两套接口，curl_cffi impersonate="chrome" 直连（原生 httpx 被指纹层拒）：

- REST v1（GET API_BASE/**，2026-09 实测最小头集）：
  必需 cookie + x-csrftoken（取 cookie csrftoken）+ x-ig-app-id（缺任一 403/404）；
  x-ig-www-claim / x-web-session-id / rur 等会话头均可省。
  * 收藏：feed/saved/posts，items 为 [{media: {...}}] 嵌套，翻页 next_max_id（不透明 token）
  * 关注：friendships/{ds_user_id}/following，max_id 为纯偏移量（首页 "12"、次页 "24"）
  * 详情：media/{pk}/info → items[0]（play_info / 直链解析共用）
- GraphQL（POST /graphql/query，form-urlencoded）：
  form 最小集 lsd/variables/doc_id（av / fb_dtsg / __dyn 等全可省，实测）；
  variables 必须带 username + 3 个 Polaris pv 标志（constants.USER_POSTS_PV_FLAGS），
  投稿查询不认数字 pk；翻页回传 after = page_info.end_cursor（"{media_pk}_{user_pk}"）。
  lsd 令牌从 instagram.com 任意页面 HTML 提取（"LSD",[],{"token":"..."}，threads 同款）。

登录态复用账号浏览器 profile：起一次无头 Chromium 读 instagram.com 域 cookies
（ctx.cookies(urls=[...]) 按域过滤；profile 若同时登录 Threads，共享 cookie 不会混入）。
Instagram 需代理出网：与 threads 同策略（env → Windows 注册表）。

CDN（scontent-*.cdninstagram.com）头像/封面/视频直链实测仅 UA 即可访问（Range 206 验证）。
博主主键（follow_authors.sec_uid）= username：投稿 GraphQL 只认 username，全局唯一且与
主页 URL 一致；数字 pk 存 uid 列（关注列表 / 作品响应自动回填，防改名漂移）。
"""
import asyncio
import json
import logging
import os
import re
import time

from curl_cffi import requests
from curl_cffi.requests.exceptions import HTTPError, RequestException

from app.services import browser
from . import constants
from .parser import (
    parse_following_list,
    parse_media_info,
    parse_play_info,
    parse_saved_list,
    parse_user_posts,
)
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.instagram.api")

_LSD_PATTERN = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')
_HTTP_RETRIES = 3  # 连接瞬断重试次数（本地代理不稳，SSL reset 常见）
_AUTH_MESSAGES = ("login_required", "authentication_required", "Not authorized")


def resolve_proxy() -> str | None:
    """代理地址：优先环境变量；Windows 桌面代理回退注册表 Internet Settings。

    与 ThreadsAdapter 直连同策略（env → 注册表），供直连与浏览器会话共用。
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
                    server = "http://" + str(server)
                return server
        except (OSError, ImportError, ValueError):
            pass
    return None


def _cookie_value(cookie_header: str, name: str) -> str:
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


async def profile_cookie_header(profile_path: str) -> str:
    """从持久化浏览器 profile 读取 instagram.com 域 cookies 拼 cookie 头。

    无登录 cookie 时抛 LoginExpiredError（与浏览器模式同一判定）。
    """
    async with browser.session(profile_path, headless=True, proxy=resolve_proxy()) as ctx:
        cookies = await ctx.cookies(urls=[constants.HOME_URL])
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("Instagram 登录态缺失（profile 无 sessionid），请重新登录")
    return header


def _http_with_retry(fn, *args, **kwargs):
    """curl 请求连接瞬断（SSL reset / 超时，本地代理不稳）自动重试。

    仅重试连接类 RequestException（GET 幂等，重试安全）；
    HTTP 状态错误（HTTPError）不重试直接抛。
    """
    last_exc: Exception | None = None
    for attempt in range(1, _HTTP_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except HTTPError:
            raise
        except RequestException as exc:
            last_exc = exc
            logger.warning("请求连接失败（第 %d/%d 次）：%s", attempt, _HTTP_RETRIES, exc)
            if attempt < _HTTP_RETRIES:
                time.sleep(attempt)  # 1s, 2s 退避
    raise last_exc


def _base_headers(cookie_header: str, referer: str) -> dict:
    """REST v1 / GraphQL 共用的最小头集（实测必需项见模块 docstring）。"""
    return {
        "accept": "*/*",
        "cookie": cookie_header,
        "referer": referer,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
        "x-asbd-id": "359341",
        # 缺失时网关直接 403（实测）
        "x-csrftoken": _cookie_value(cookie_header, "csrftoken"),
        "x-ig-app-id": constants.APP_ID,
        "x-ig-max-touch-points": "0",
        "x-requested-with": "XMLHttpRequest",
    }


def _check_auth(response) -> None:
    """登录态失效判定：401/403 或 body 报 login_required → LoginExpiredError。"""
    if response.status_code in (401, 403):
        raise LoginExpiredError(
            f"Instagram 登录态已失效（HTTP {response.status_code}），请重新登录")
    message = str((response.json() or {}).get("message") or "") \
        if "json" in (response.headers.get("content-type") or "") else ""
    if any(t in message for t in _AUTH_MESSAGES):
        raise LoginExpiredError(f"Instagram 登录态已失效（{message}），请重新登录")


def _v1_get(cookie_header: str, url: str, referer: str) -> dict:
    """GET 一个 REST v1 接口并返回 JSON（同步阻塞，异步侧 asyncio.to_thread 调用）。"""
    response = _http_with_retry(
        requests.get, url,
        headers=_base_headers(cookie_header, referer),
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    _check_auth(response)
    response.raise_for_status()
    return response.json()


def fetch_lsd(cookie_header: str) -> str:
    """GET 首页 HTML 提取 lsd 令牌（同步阻塞，异步侧用 asyncio.to_thread 调用）。"""
    response = _http_with_retry(
        requests.get, constants.HOME_URL,
        headers={"cookie": cookie_header,
                 "user-agent": _base_headers(cookie_header, "")["user-agent"]},
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    match = _LSD_PATTERN.search(response.text)
    if not match:
        raise RuntimeError("未能从 Instagram 页面提取 lsd 令牌（页面结构变化或登录态失效）")
    return match.group(1)


def _graphql_post(cookie_header: str, lsd: str, friendly_name: str,
                  root_field: str, variables: dict, doc_id: str) -> dict:
    """POST /graphql/query 公共实现（同步阻塞）。

    最小必需：form 的 lsd/variables/doc_id + 头 x-csrftoken（缺 403）、
    x-fb-lsd、x-ig-app-id、x-fb-friendly-name、x-root-field-name；
    av / fb_dtsg / __dyn 等实测可省（2026-09）。
    """
    form = {
        "lsd": lsd,
        "variables": _json_compact(variables),
        "doc_id": doc_id,
        "server_timestamps": "true",
    }
    headers = _base_headers(cookie_header, constants.HOME_URL)
    headers.update({
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.instagram.com",
        "x-fb-lsd": lsd,
        "x-fb-friendly-name": friendly_name,
        "x-root-field-name": root_field,
    })
    response = _http_with_retry(
        requests.post, constants.GRAPHQL_URL, data=form, headers=headers,
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    _check_auth(response)
    response.raise_for_status()
    return response.json()


def _json_compact(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


# ---------- 收藏列表（fetch/task 体系）----------

def fetch_saved_page(cookie_header: str, max_id: str = "") -> dict:
    """拉取一页收藏列表（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    max_id 为上一页响应的 next_max_id（首页传空）；
    返回 parse_saved_list 的结果 {items, cursor, has_more}。
    """
    params = f"count={constants.SAVED_PAGE_COUNT}"
    if max_id:
        params += f"&max_id={max_id}"
    data = _v1_get(cookie_header, f"{constants.API_BASE}{constants.SAVED_PATH}?{params}",
                   constants.HOME_URL)
    return parse_saved_list(data)


async def fetch_saved(cookie_header: str, count: int, on_batch=None):
    """按 next_max_id 游标翻页拉取收藏列表，直到取满 count（0=全部）或 more_available=false。

    返回 (全部 items, 最后一批的 has_more)；on_batch({"page", "items"}) 逐页回调。
    """
    max_id = ""
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(fetch_saved_page, cookie_header, max_id)
        page += 1
        collected.extend(batch["items"])
        logger.info(
            "saved 第 %d 页：%d 条，累计 %d，has_more=%s",
            page, len(batch["items"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"] or not batch["cursor"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        max_id = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


# ---------- 特别关注（follows）体系：关注列表 / 博主主页作品 ----------

def self_user_id(cookie_header: str) -> str:
    """当前登录账号的用户 id（cookie ds_user_id，REST v1 friendships 用它定位）。"""
    return _cookie_value(cookie_header, "ds_user_id")


def fetch_following_page(cookie_header: str, user_id: str, max_id: str = "") -> dict:
    """拉取一页关注列表（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    max_id 为上一页响应的 next_max_id（首页传空，纯偏移量）；
    返回 parse_following_list 的结果 {followings, cursor, has_more}。
    """
    params = f"count={constants.FOLLOWING_PAGE_COUNT}"
    if max_id:
        params += f"&max_id={max_id}"
    data = _v1_get(
        cookie_header,
        f"{constants.API_BASE}{constants.FOLLOWING_PATH.format(user_id=user_id)}?{params}",
        constants.HOME_URL,
    )
    return parse_following_list(data)


async def fetch_followings(cookie_header: str, user_id: str, count: int = 0,
                           on_batch=None):
    """按 next_max_id 翻页拉取关注列表，直到取满 count（0=全部）或 has_more=false。

    返回 (全部 followings, 最后一批的 has_more)；on_batch({"page", "followings"}) 逐页回调。
    """
    max_id = ""
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(
            fetch_following_page, cookie_header, user_id, max_id)
        page += 1
        collected.extend(batch["followings"])
        logger.info(
            "followings 第 %d 页：%d 条，累计 %d，has_more=%s",
            page, len(batch["followings"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["followings"]:
            await on_batch({"page": page, "followings": batch["followings"]})
        if not batch["has_more"] or not batch["cursor"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        max_id = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


def fetch_user_posts_page(cookie_header: str, lsd: str, username: str,
                          after: str = "", first: int = 0) -> dict:
    """拉取一页博主主页作品（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    after 为上一页响应的 end_cursor（首页传空）；first 每页条数（0 =
    constants.USER_POSTS_PAGE_COUNT）；返回 parse_user_posts 的结果 {items, cursor, has_more}。
    """
    n = first or constants.USER_POSTS_PAGE_COUNT
    variables = {
        "before": None, "last": None, "username": username,
        "first": n, "include_multi_captions": True,
        # data.count 与抓包保持一致（内层计数，实测跟随 first 生效）
        "data": {"count": n, "include_reel_media_seen_timestamp": True,
                 "include_relationship_info": True, "latest_besties_reel_media": True,
                 "latest_reel_media": True},
        **constants.USER_POSTS_PV_FLAGS,
    }
    if after:
        variables["after"] = after
    data = _graphql_post(cookie_header, lsd, constants.USER_POSTS_QUERY_NAME,
                         constants.USER_POSTS_ROOT_FIELD, variables,
                         constants.USER_POSTS_DOC_ID)
    conn = (data.get("data") or {}).get(constants.USER_POSTS_ROOT_FIELD)
    if conn is None:
        errors = "; ".join(str(e.get("message")) for e in (data.get("errors") or []))
        raise RuntimeError(f"博主作品查询失败（@{username}）：{errors or str(data)[:200]}")
    return parse_user_posts(data)


async def fetch_user_posts(cookie_header: str, username: str, count: int = 0,
                           on_batch=None):
    """按 end_cursor 游标翻页拉取博主主页作品，直到取满 count（0=全部）或 has_more=false。

    返回 (全部 items, 最后一批的 has_more)；on_batch({"page", "items"}) 逐页回调。
    """
    after = ""
    collected: list[dict] = []
    page = 0
    lsd = await asyncio.to_thread(fetch_lsd, cookie_header)
    while True:
        batch = await asyncio.to_thread(
            fetch_user_posts_page, cookie_header, lsd, username, after)
        page += 1
        collected.extend(batch["items"])
        logger.info(
            "user_posts 第 %d 页：%d 条，累计 %d，has_more=%s",
            page, len(batch["items"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"] or not batch["cursor"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        after = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


def fetch_media_info(cookie_header: str, media_id: str) -> dict:
    """拉取作品详情（REST v1 media/{pk}/info → items[0]，同步阻塞）。

    follows_play_info（parse_play_info）与通用 content 行（parse_media_info）共用。
    """
    data = _v1_get(
        cookie_header,
        f"{constants.API_BASE}{constants.MEDIA_INFO_PATH.format(media_id=media_id)}",
        constants.HOME_URL,
    )
    items = data.get("items") or []
    if not items:
        raise RuntimeError(f"作品详情为空（{media_id}，可能已删除或不可见）")
    return items[0]


# ---------- 播放信息（follows_play_info 的同步内核）----------

def fetch_play_info(cookie_header: str, media_id: str) -> dict:
    """作品详情 → PlayerModal 统一结构（同步阻塞，异步侧用 asyncio.to_thread 调用）。"""
    return parse_play_info(fetch_media_info(cookie_header, media_id))
