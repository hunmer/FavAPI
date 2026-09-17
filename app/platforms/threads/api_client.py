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
from urllib.parse import urlencode

from curl_cffi import requests

from app.services import browser
from . import constants
from .parser import parse_saved_media, parse_viewer_profile
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.threads.api")

_LSD_PATTERN = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')


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


def _fetch_saved_html(cookie_header: str) -> str:
    """GET /saved 页面 HTML（同步阻塞）：lsd 令牌与当前用户身份都从这里提取。"""
    response = requests.get(
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


def fetch_saved_page(cookie_header: str, lsd: str, after: str = "") -> dict:
    """拉取一页收藏列表（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    after 为上一页响应的 end_cursor（首页传空）；
    返回 parse_saved_media 的结果 {items, cursor, has_more}。
    """
    variables = {"first": constants.API_PAGE_COUNT, **constants.SAVED_PV_FLAGS}
    if after:
        variables["after"] = after
    form = {
        "av": constants.APP_VIEWER_ID,
        "lsd": lsd,
        "variables": json.dumps(variables, separators=(",", ":")),
        "doc_id": constants.SAVED_DOC_ID,
        "server_timestamps": "true",
    }
    response = requests.post(
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
            "x-fb-friendly-name": constants.SAVED_QUERY_NAME,
            # 缺失时网关直接 403（实测）
            "x-csrftoken": _cookie_value(cookie_header, "csrftoken"),
        },
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    data = response.json()
    media = ((data.get("data") or {}).get("xdt_text_app_viewer") or {}).get("saved_media")
    if media is None:
        errors = "; ".join(str(e.get("message")) for e in (data.get("errors") or []))
        raise RuntimeError(f"saved_media 查询失败：{errors or response.text[:200]}")
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
