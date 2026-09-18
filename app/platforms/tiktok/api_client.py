"""TikTok 收藏/点赞列表 API 直连客户端。

TikTok Web 列表接口 2026-09 逆向结论（用户抓包 + curl_cffi 消融实验）：
- TLS/HTTP2 指纹层不拦截 curl_cffi（impersonate="chrome" 直连正常返回 JSON）；
- 签名参数不做强校验：X-Gnarly / X-Bogus / msToken / X-Dynosaur / verifyFp
  单独缺失均可通过（与抖音 a_bogus 同款宽松策略），但 query 需保留
  msToken（cookie 现值即可）+ X-Bogus=1 占位 —— 签名参数全部删除会触发
  HTTP 200 + 空响应的软拦截；
- 收藏接口 /api/user/collect/item_list/ 强登录态校验：会话失效返回
  status_code=8 "Login expired"（转为 LoginExpiredError，由任务执行器
  标记账号 expired）；实测复制出浏览器的 cookie 数分钟后即被该接口拒绝，
  必须用 profile 的活跃会话；
- 点赞接口 /api/favorite/item_list/ 半公开：仅公开点赞的用户可见，
  私密点赞（默认设置）即使本人会话也返回空列表，非报错；
- 翻页 cursor 为服务端返回的毫秒时间戳（首页传 0），hasMore 布尔收尾；
- 帖子详情（视频/图文下载直链）：/api/item/detail XHR 有签名强校验
  （X-Gnarly 与完整 query 绑定，改任一参数即空响应），不可直连；改走帖子页
  HTML 的 SSR 段 webapp.video-detail（公开访客可见），图文帖必须用 /video/
  路径访问才有该段；视频 CDN 直链需页面会话 cookie（tt_chain_token），
  v16 主机对部分出口 IP 403、v19 可用（见 fetch_post_detail）。

列表接口都要求 secUid 入参：无 cookie 可得（TikTok 不写 secUid cookie），
在登录后由 adapter.refresh_profile 从个人主页 HTML 提取并回填账号 extra，
运行期也可从 /favorites SSR 现提取兜底。

tiktok.com 在部分网络环境需代理：与声明式平台同策略解析（env → Windows
注册表），浏览器会话与直连共用。
"""
import asyncio
import logging
import os
import re
from urllib.parse import urlencode

from curl_cffi import requests
from curl_cffi.requests.exceptions import HTTPError, RequestException

from app.services import browser
from . import constants
from .parser import (
    parse_download_links,
    parse_item_detail_html,
    parse_item_list,
    parse_user_detail_html,
)
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.tiktok.api")

_SEC_UID_PATTERN = re.compile(r'"secUid":"(MS4wLjAB[A-Za-z0-9_.-]+)"')

_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-TW,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,en-GB;q=0.6,en-US;q=0.5",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": constants.USER_AGENT,
}

# 抓包所得浏览器公共 query（保持与浏览器一致最稳；服务端按风控而非内容校验）。
# 签名位（msToken/X-Bogus）在 _list_params 内按请求补齐。
_QUERY_PARAMS = {
    "WebIdLastTime": "1789635966",
    "aid": "1988",
    "app_language": "en",
    "app_name": "tiktok_web",
    "browser_language": "en-TW",
    "browser_name": "Mozilla",
    "browser_online": "true",
    "browser_platform": "Win32",
    "browser_version": constants.USER_AGENT.split("Mozilla/5.0 ", 1)[1],
    "channel": "tiktok_web",
    "cookie_enabled": "true",
    "coverFormat": "2",
    "data_collection_enabled": "true",
    "device_id": "7686427028757628446",
    "device_platform": "web_pc",
    "focus_state": "true",
    "from_page": "user",
    "history_len": "5",
    "is_fullscreen": "false",
    "is_page_visible": "true",
    "language": "en",
    "needPinnedItemIds": "true",
    "os": "windows",
    "post_item_list_request_type": "0",
    "priority_region": "US",
    "region": "US",
    "root_referer": "",
    "screen_height": "1080",
    "screen_width": "1920",
    "tz_name": "Asia/Shanghai",
    "user_is_login": "true",
    "verifyFp": "",
    "video_encoding": "dash",
    "webcast_language": "en",
}


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
                    server = "http://" + server
                return server
        except (OSError, ImportError, ValueError):
            pass
    return None


def _cookie_value(cookie_header: str, name: str) -> str:
    """cookie 头里取指定名字的值（同名多条取最后一条，与浏览器末值生效一致）。"""
    value = ""
    for part in cookie_header.split(";"):
        key, _, val = part.strip().partition("=")
        if key == name:
            value = val
    return value


async def profile_cookie_header(profile_path: str) -> str:
    """从持久化浏览器 profile 读取 tiktok.com cookies 拼 cookie 头。

    无登录 cookie 时抛 LoginExpiredError（与浏览器模式同一判定）。
    """
    async with browser.session(profile_path, headless=True, proxy=resolve_proxy()) as ctx:
        cookies = await ctx.cookies(urls=[constants.HOME_URL])
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("TikTok 登录态缺失（profile 无 sessionid），请重新登录")
    return header


def _list_params(cookie_header: str, sec_uid: str, cursor: int, count: int) -> dict:
    """列表接口 query：浏览器公共参数 + secUid/翻页 + 签名占位。"""
    return {
        **_QUERY_PARAMS,
        "secUid": sec_uid,
        "count": count,
        "cursor": cursor,
        "referer": constants.HOMEPAGE,
        # 签名位不做内容校验但需存在：msToken 用 cookie 现值，X-Bogus 恒为 1（浏览器现状）
        "msToken": _cookie_value(cookie_header, "msToken") or "0",
        "X-Bogus": "1",
    }


def _check_list_response(data: dict, api: str) -> dict:
    """列表响应统一校验：status_code=8 登录失效；statusCode 非 0 视为接口错误。"""
    if data.get("status_code") == 8 or data.get("status_msg") == "Login expired":
        raise LoginExpiredError("TikTok 登录态失效（会话被拒绝），请重新登录")
    status_code = data.get("statusCode")
    if status_code not in (0, None):
        raise RuntimeError(f"{api} 返回错误 statusCode={status_code}")
    return data


def _request_page(url: str, params: dict, cookie_header: str, referer: str) -> dict:
    """GET 单页并校验（同步阻塞，异步侧用 asyncio.to_thread 调用）。"""
    response = requests.get(
        url + "?" + urlencode(params),
        headers={**_HEADERS, "cookie": cookie_header, "referer": referer},
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    if not response.text.strip():
        # 空响应 = 风控/指纹层软拦截（签名位缺失或出口 IP 信誉问题）
        raise RuntimeError(f"TikTok 返回空响应（疑似风控拦截），请稍后重试或更换代理出口")
    return response.json()


def fetch_collect_page(cookie_header: str, sec_uid: str, cursor: int = 0,
                        count: int = constants.API_PAGE_COUNT) -> dict:
    """拉取一页收藏列表（同步阻塞）。返回 parse_item_list 的结果。"""
    data = _request_page(
        constants.COLLECT_LIST_URL,
        _list_params(cookie_header, sec_uid, cursor, count),
        cookie_header, constants.HOME_URL,
    )
    return parse_item_list(_check_list_response(data, "collect/item_list"))


def fetch_favorite_page(cookie_header: str, sec_uid: str, cursor: int = 0,
                         count: int = constants.API_PAGE_COUNT) -> dict:
    """拉取一页点赞列表（同步阻塞）。返回 parse_item_list 的结果。"""
    data = _request_page(
        constants.LIKE_LIST_URL,
        _list_params(cookie_header, sec_uid, cursor, count),
        cookie_header, constants.HOME_URL,
    )
    return parse_item_list(_check_list_response(data, "favorite/item_list"))


async def _fetch_pages(page_fn, cookie_header: str, sec_uid: str, count: int, on_batch,
                       label: str):
    """按毫秒时间戳游标翻页，直到取满 count（0=全部）或 hasMore=false。

    返回 (全部 items, 最后一批的 has_more)。
    """
    cursor = 0
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(
            page_fn, cookie_header, sec_uid, cursor, constants.API_PAGE_COUNT
        )
        page += 1
        collected.extend(batch["items"])
        logger.info(
            "%s 第 %d 页：%d 条，累计 %d，hasMore=%s",
            label, page, len(batch["items"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"] or not batch["cursor"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        cursor = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


async def fetch_collect(cookie_header: str, sec_uid: str, count: int, on_batch=None):
    """翻页拉取收藏列表。"""
    return await _fetch_pages(fetch_collect_page, cookie_header, sec_uid, count,
                              on_batch, "collect")


async def fetch_favorite(cookie_header: str, sec_uid: str, count: int, on_batch=None):
    """翻页拉取点赞列表。"""
    return await _fetch_pages(fetch_favorite_page, cookie_header, sec_uid, count,
                              on_batch, "favorite")


def fetch_user_detail(handle: str, cookie_header: str | None = None) -> dict:
    """获取用户信息：解析个人主页 HTML 的服务端渲染数据（公开，访客可用）。

    /api/user/detail/ 接口对非浏览器上下文返回空 userInfo（实测），HTML 路径稳定。
    注意：带登录 cookie 时该页 SSR 结构可能不含 webapp.user-detail（实测），
    查他人请不传 cookie；本人信息用 fetch_app_context。
    """
    response = requests.get(
        f"{constants.HOMEPAGE}/@{handle}",
        headers={**_HEADERS, **({"cookie": cookie_header} if cookie_header else {})},
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    info = parse_user_detail_html(response.text)
    if not info:
        raise RuntimeError(f"解析 TikTok 用户信息失败：@{handle}（页面结构变化或被风控拦截）")
    return info


def fetch_post_detail(item_id: str) -> dict:
    """按 item_id 拉取帖子详情并解析可下载直链（同步阻塞，异步侧 to_thread 调用）。

    JS Reverse 2026-09 结论：详情 XHR /api/item/detail 有签名强校验
    （X-Gnarly 与完整 query 绑定，改动任一参数即 HTTP 200 空响应），不可直连；
    可用数据源是帖子页 HTML 的服务端渲染段 webapp.video-detail（公开，访客
    可见）。图文帖必须以 /video/{id} 路径访问才有该段（/photo/ 路径不渲染，
    /embed 页无完整数据），URL 中 handle 不参与定位（占位即可）。

    视频直链（v16/v19-webapp-prime CDN）下载需页面会话 cookie（tt_chain_token，
    URL 内 tk=tt_chain_token 对应），实测仅 UA 或仅 ttwid 均 403 —— 会话 cookie
    随返回值 cookie_header 下发，由调用方注入下载请求头；v16 主机对部分出口
    IP 拒绝（403），parser 已优先 v19 URL。
    返回 {"item_id", "links", "cookie_header", "author_name", "author_id"}。
    """
    if not str(item_id).isdigit():
        raise ValueError(f"TikTok 帖子 ID 需为纯数字：{item_id}")
    url = constants.POST_DETAIL_URL.format(item_id=item_id)
    logger.info("fetch_post_detail 请求：item_id=%s", item_id)
    session = requests.Session()
    response = session.get(
        url,
        headers={**_HEADERS, "accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    item = parse_item_detail_html(response.text)
    if not item:
        raise RuntimeError(
            f"解析 TikTok 帖子详情失败：{item_id}（作品可能已删除/设为私密，或页面结构变化）")
    links = parse_download_links(item)
    if not links:
        raise RuntimeError("详情响应无可下载内容（作品可能已删除或设为私密）")
    cookie_header = "; ".join(f"{c.name}={c.value}" for c in session.cookies.jar)
    author = item.get("author") or {}
    return {
        "item_id": str(item.get("id") or item_id),
        "links": links,
        "cookie_header": cookie_header,
        "author_name": author.get("nickname"),
        "author_id": str(author.get("uniqueId") or author.get("id") or ""),
    }


def fetch_app_context(cookie_header: str) -> dict:
    """获取当前登录用户信息（JS Reverse 定位：webapp 身份即本接口的 user 段）。

    GET /node-webapp/api/common-app-context（无签名要求，登录 cookie 直连可用），
    返回 {user_id, sec_uid, unique_id, nickname, avatar, signature, odin_id}。
    未登录时响应无 user 段，抛 LoginExpiredError。
    """
    response = requests.get(
        constants.APP_CONTEXT_URL,
        headers={**_HEADERS, "cookie": cookie_header, "referer": constants.HOMEPAGE},
        impersonate="chrome", timeout=30, proxy=resolve_proxy(),
    )
    response.raise_for_status()
    data = response.json()
    user = data.get("user") or {}
    if not user.get("secUid"):
        raise LoginExpiredError("TikTok 登录态失效（common-app-context 无用户信息），请重新登录")
    avatar_uri = user.get("avatarUri")
    if isinstance(avatar_uri, list):  # 头像字段原生是 URL 列表，取首个
        avatar_uri = avatar_uri[0] if avatar_uri else None
    return {
        "user_id": str(user.get("uid") or ""),
        "sec_uid": user.get("secUid"),
        "unique_id": user.get("uniqueId"),
        "nickname": user.get("nickName"),
        "avatar": avatar_uri,
        "signature": user.get("signature"),
        "odin_id": str(data.get("odinId") or ""),
    }


def resolve_self_sec_uid(cookie_header: str) -> str | None:
    """当前账号 secUid：优先 common-app-context，失败回退 foryou SSR 解析。

    SSR 备用通道同样来自 webapp.app-context（服务端渲染内嵌），访客页面无 user 段。
    """
    try:
        return fetch_app_context(cookie_header)["sec_uid"]
    except (LoginExpiredError, HTTPError, RequestException, RuntimeError, ValueError) as exc:
        logger.warning("common-app-context 获取身份失败，回退 foryou SSR：%s", exc)
    try:
        response = requests.get(
            f"{constants.HOMEPAGE}/foryou",
            headers={**_HEADERS, "cookie": cookie_header,
                     "accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
            impersonate="chrome", timeout=30, proxy=resolve_proxy(),
        )
        response.raise_for_status()
    except (HTTPError, RequestException) as exc:
        logger.warning("resolve_self_sec_uid 请求失败：%s", exc)
        return None
    match = _SEC_UID_PATTERN.search(response.text)
    return match.group(1) if match else None
