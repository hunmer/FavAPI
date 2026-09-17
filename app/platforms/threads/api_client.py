"""Threads 收藏（saved）API 直连客户端。

Threads Web 走 GraphQL（POST /graphql/query，form-urlencoded）：
- TLS/HTTP2 指纹层有校验（原生 httpx 被拒），用 curl_cffi impersonate="chrome" 直连；
- POST 必须带 x-csrftoken 头（取 cookie csrftoken），缺失直接 403；
- variables 必须带完整的 relay pv 标志（constants.SAVED_PV_FLAGS），缺失报 GraphQL execution error；
- lsd 令牌从 /saved 页面 HTML 提取（"LSD",[],{"token":"..."}），每次会话现取。

登录态复用账号浏览器 profile：起一次无头 Chromium 读出 threads.com 域 cookies
（profile 同时含 instagram.com 同名 cookie，必须按域过滤），后续请求纯 HTTP。
threads.com 在部分网络环境需代理：与声明式平台同策略解析（env → Windows 注册表）。
"""
import asyncio
import json
import logging
import os
import re
import time
from urllib.parse import urlencode

from curl_cffi import requests
from curl_cffi.requests.exceptions import HTTPError, RequestException

from app.services import browser
from . import constants
from .parser import parse_saved_media, parse_viewer_profile
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.threads.api")

_LSD_PATTERN = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')
_HTTP_RETRIES = 3  # 连接瞬断重试次数（本地代理不稳，SSL reset 常见）


def resolve_proxy() -> str | None:
    """代理地址：优先环境变量；Windows 桌面代理回退注册表 Internet Settings。

    与 DeclarativeAdapter._proxy 的 'auto' 逻辑一致，供直连与浏览器会话共用。
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
    """从持久化浏览器 profile 读取 threads.com 域 cookies 拼 cookie 头。

    无登录 cookie 时抛 LoginExpiredError（与浏览器模式同一判定）。
    """
    async with browser.session(profile_path, headless=True, proxy=resolve_proxy()) as ctx:
        cookies = await ctx.cookies(urls=[constants.FAVORITES_URL])
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("Threads 登录态缺失（profile 无 sessionid），请重新登录")
    return header


def _http_with_retry(fn, *args, **kwargs):
    """curl 请求连接瞬断（SSL reset / 超时，本地代理不稳）自动重试。

    仅重试连接类 RequestException（save/unsave 等写操作幂等，重试安全）；
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


def _fetch_saved_html(cookie_header: str) -> str:
    """GET /saved 页面 HTML（同步阻塞）：lsd 令牌与当前用户身份都从这里提取。"""
    response = _http_with_retry(
        requests.get,
        constants.FAVORITES_URL,
        headers={"cookie": cookie_header},
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    return response.text


def fetch_lsd(cookie_header: str) -> str:
    """GET /saved 页面提取 lsd 令牌（同步阻塞，异步侧用 asyncio.to_thread 调用）。"""
    match = _LSD_PATTERN.search(_fetch_saved_html(cookie_header))
    if not match:
        raise RuntimeError("未能从 Threads 收藏页提取 lsd 令牌（页面结构变化或登录态失效）")
    return match.group(1)


def fetch_viewer_profile(cookie_header: str) -> dict:
    """获取当前登录用户身份（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    从 /saved 页面 HTML 的 BarcelonaSharedData 提取 {id, username, avatar}；
    未登录（会话失效被重定向）时该块无 viewer → 抛 LoginExpiredError。
    """
    profile = parse_viewer_profile(_fetch_saved_html(cookie_header))
    if profile is None:
        raise LoginExpiredError("Threads 登录态已失效（会话无 viewer 信息），请重新登录")
    return profile


def _graphql_post(cookie_header: str, lsd: str, friendly_name: str,
                  variables: dict, doc_id: str) -> dict:
    """POST /graphql/query 公共实现（同步阻塞）。

    最小必需：form 的 av/lsd/variables/doc_id + 头 x-csrftoken（缺 403）、
    x-fb-lsd、x-ig-app-id、x-fb-friendly-name；返回响应 JSON。
    """
    form = {
        "av": constants.APP_VIEWER_ID,
        "lsd": lsd,
        "variables": json.dumps(variables, separators=(",", ":")),
        "doc_id": doc_id,
        "server_timestamps": "true",
    }
    response = _http_with_retry(
        requests.post,
        constants.GRAPHQL_URL,
        data=urlencode(form),
        headers={
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.threads.com",
            "referer": constants.FAVORITES_URL,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "cookie": cookie_header,
            "x-fb-lsd": lsd,
            "x-ig-app-id": constants.APP_ID,
            "x-fb-friendly-name": friendly_name,
            # 缺失时网关直接 403（实测）
            "x-csrftoken": _cookie_value(cookie_header, "csrftoken"),
        },
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    return response.json()


def fetch_saved_page(cookie_header: str, lsd: str, after: str = "") -> dict:
    """拉取一页收藏列表（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    after 为上一页响应的 end_cursor（首页传空）；
    返回 parse_saved_media 的结果 {items, cursor, has_more}。
    """
    variables = {"first": constants.API_PAGE_COUNT, **constants.SAVED_PV_FLAGS}
    if after:
        variables["after"] = after
    data = _graphql_post(cookie_header, lsd, constants.SAVED_QUERY_NAME,
                         variables, constants.SAVED_DOC_ID)
    media = ((data.get("data") or {}).get("xdt_text_app_viewer") or {}).get("saved_media")
    if media is None:
        errors = "; ".join(str(e.get("message")) for e in (data.get("errors") or []))
        raise RuntimeError(f"saved_media 查询失败：{errors or str(data)[:200]}")
    return parse_saved_media(data)


async def fetch_saved(cookie_header: str, count: int, on_batch=None):
    """按 end_cursor 游标翻页拉取收藏列表，直到取满 count（0=全部）或 has_more=false。

    返回 (全部 items, 最后一批的 has_more)。
    """
    after = ""
    collected: list[dict] = []
    page = 0
    lsd = await asyncio.to_thread(fetch_lsd, cookie_header)
    while True:
        batch = await asyncio.to_thread(fetch_saved_page, cookie_header, lsd, after)
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
        after = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


def _mutation_media(cookie_header: str, lsd: str, doc_id: str, friendly_name: str,
                    media_id: str) -> dict:
    """执行收藏/取消收藏 mutation（同步阻塞），返回 data.data.media。"""
    data = _graphql_post(cookie_header, lsd, friendly_name,
                         {"media_id": str(media_id), "module": constants.SAVE_MODULE}, doc_id)
    media = ((data.get("data") or {}).get("data") or {}).get("media")
    if media is None:
        errors = "; ".join(str(e.get("message")) for e in (data.get("errors") or []))
        raise RuntimeError(f"mutation 失败（media_id={media_id}）：{errors or str(data)[:200]}")
    return media


def save_media(cookie_header: str, lsd: str, media_id: str) -> dict:
    """收藏帖子（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    media_id 为帖子 pk（收藏列表 content_id）；成功响应 has_viewer_saved=True。
    """
    media = _mutation_media(cookie_header, lsd, constants.SAVE_DOC_ID,
                            constants.SAVE_QUERY_NAME, media_id)
    logger.info("save_media media_id=%s has_viewer_saved=%s", media_id, media.get("has_viewer_saved"))
    return media


def unsave_media(cookie_header: str, lsd: str, media_id: str) -> dict:
    """取消收藏帖子（同步阻塞）；成功响应 has_viewer_saved=null。"""
    media = _mutation_media(cookie_header, lsd, constants.UNSAVE_DOC_ID,
                            constants.UNSAVE_QUERY_NAME, media_id)
    logger.info("unsave_media media_id=%s has_viewer_saved=%s", media_id, media.get("has_viewer_saved"))
    return media


async def unsave_multi(cookie_header: str, media_ids: list[str], on_progress=None) -> dict:
    """批量取消收藏：共用一次 lsd 逐条执行，间隔 UNSAVE_INTERVAL_SEC。

    返回 {total, canceled}；on_progress({"batch_no", "total_batches", "done", "ids"})
    逐条回调进度。
    """
    lsd = await asyncio.to_thread(fetch_lsd, cookie_header)
    canceled = 0
    for i, media_id in enumerate(media_ids, start=1):
        await asyncio.to_thread(unsave_media, cookie_header, lsd, media_id)
        canceled += 1
        if on_progress:
            await on_progress({
                "batch_no": i, "total_batches": len(media_ids),
                "done": canceled, "ids": [media_id],
            })
        if i < len(media_ids):
            await asyncio.sleep(constants.UNSAVE_INTERVAL_SEC)
    return {"total": len(media_ids), "canceled": canceled}
