"""抖音收藏/喜欢列表 API 客户端。

抖音按客户端 TLS/HTTP2 指纹拦截非浏览器请求（node/Go/原生 httpx 均返回空响应），
读接口（listcollection / favorite）用 curl-impersonate（curl_cffi impersonate="chrome"）
完整模拟 Chrome 指纹直连即可。

写接口（digg / cancel digg 等）2026-09 起启用 JS 签名强校验（a_bogus / bd-ticket-guard），
curl_cffi 直连无论何种 cookie/指纹组合一律被拒；必须在真实浏览器页面上下文发请求，
由页面 fetch hook 自动加签（*_via_browser 系列函数）。

登录态复用账号的浏览器 profile：起一次无头 Chromium 读出 cookies 后关闭，
后续翻页全部走纯 HTTP。
"""
import asyncio
import json
import logging
from urllib.parse import urlencode

from curl_cffi import requests

from app.services import browser
from . import constants
from .parser import parse_history, parse_like_list, parse_listcollection, parse_watchlater
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.douyin.api")

# 收藏页收藏 tab 抓包所得公共 query（保持与浏览器一致最稳；服务端按风控而非内容校验）
_QUERY_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "publish_video_strategy_type": "2",
    "pc_client_type": "1",
    "pc_libra_divert": "Windows",
    "update_version_code": "170400",
    "support_h265": "1",
    "support_dash": "1",
    "version_code": "170400",
    "version_name": "17.4.0",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "151.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "151.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": "12",
    "device_memory": "32",
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "round_trip_time": "50",
}

_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "referer": "https://www.douyin.com/user/self?showTab=favorite_collection",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    # 浏览器在未通过 secsdk 挑战时发送的降级标记，直连同值即可
    "x-secsdk-csrf-token": "DOWNGRADE",
}


async def profile_cookie_header(profile_path: str) -> str:
    """从持久化浏览器 profile 读取 douyin.com cookies 拼 cookie 头。

    无登录 cookie 时抛 LoginExpiredError（与浏览器模式同一判定）。
    统一走 browser.session()：channel/并发上限/同 profile 串行锁一处维护，
    避免与抓取会话同时打开同一 profile。
    """
    async with browser.session(profile_path, headless=True) as ctx:
        cookies = await ctx.cookies()
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("抖音登录态缺失（profile 无 sessionid），请重新扫码登录")
    return header


def self_sec_uid(cookie_header: str) -> str | None:
    """从 cookie 的关注黄点信息提取当前账号 sec_user_id（FOLLOW_*_POINT_INFO 首段）。

    cookie 形如 "MS4wLjAB...ZFw/1789660800000/0/.../0"（URL 编码 + 引号包裹）；
    favorite 接口需要 sec_user_id 入参，优先从这里自动提取，失败由调用方兜底。
    """
    from urllib.parse import unquote

    for kv in cookie_header.split("; "):
        name, _, value = kv.partition("=")
        if name in ("FOLLOW_NUMBER_YELLOW_POINT_INFO", "FOLLOW_LIVE_POINT_INFO"):
            sec_uid = unquote(value).strip('"').split("/")[0]
            if sec_uid.startswith("MS4"):
                return sec_uid
    return None


def fetch_listcollection_page(cookie_header: str, cursor: int = 0, count: int = 20) -> dict:
    """拉取一页收藏列表（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    cursor 为上一页响应返回的游标（时间戳 token，首页传 0）；
    返回 parse_listcollection 的结果 {items, cursor, has_more, total}。
    """
    url = constants.LISTCOLLECTION_URL + "?" + urlencode(_QUERY_PARAMS)
    response = requests.post(
        url,
        data=f"count={count}&cursor={cursor}",
        headers={**_HEADERS, "cookie": cookie_header},
        impersonate="chrome",
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") != 0:
        raise RuntimeError(f"listcollection 返回错误 status_code={data.get('status_code')}")
    return parse_listcollection(data)


def _cursor_time(cursor: int):
    """服务端游标（微秒时间戳）→ 本页最后一条的真实收藏时间（aware datetime）；无效返回 None。"""
    from datetime import datetime as _dt

    if not cursor or cursor < 1e14:  # 微秒时间戳量级 1e15+，过小视为无效
        return None
    try:
        return _dt.fromtimestamp(cursor / 1e6).astimezone()
    except (OSError, OverflowError, ValueError):
        return None


async def fetch_listcollection(cookie_header: str, cursor: int, count: int, on_batch=None,
                               stop_before: "object | None" = None):
    """按服务端游标翻页直到取满 count（0=全部）或 has_more=false。

    stop_before（aware datetime）：列表按真实收藏时间倒序且收藏时间 ≥ 发布时间，
    游标即本页最后一条的收藏时间 —— 游标早于下界时后续条目的发布时间也必然早于
    下界（collected_at 兜底发布时间也不会命中），提前终止零遗漏。
    返回 (全部 items, 最后一批的 has_more)。
    """
    server_cursor = cursor
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(
            fetch_listcollection_page, cookie_header, server_cursor, constants.API_PAGE_COUNT
        )
        page += 1
        collected.extend(batch["items"])
        logger.info(
            "listcollection 第 %d 页：%d 条，累计 %d，has_more=%s",
            page, len(batch["items"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"] or not batch["cursor"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        if stop_before is not None:
            scanned_until = _cursor_time(batch["cursor"])
            if scanned_until and scanned_until < stop_before:
                logger.info("listcollection 第 %d 页游标(%s)早于下界，提前终止", page, scanned_until)
                return collected, True
        server_cursor = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


def cancel_collect_page(cookie_header: str, aweme_ids: list[str]) -> dict:
    """批量取消收藏单批（同步阻塞，异步侧用 asyncio.to_thread 调用）。

    返回接口原始响应；status_code != 0 或 fatal_ids 非空视为失败抛 RuntimeError。
    """
    type_map = {aid: 0 for aid in aweme_ids}
    body = urlencode({"aweme_ids": ",".join(aweme_ids)}) + "&" + urlencode(
        {"aweme_type_map": json.dumps(type_map, separators=(",", ":"))}
    )
    url = constants.CANCEL_COLLECT_URL + "?" + urlencode(_QUERY_PARAMS)
    logger.info("cancel_collect_page 请求：url=%s params=%s", url, body)
    response = requests.post(
        url, data=body, headers={**_HEADERS, "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    fatal_ids = data.get("fatal_ids") or []
    status_code = data.get("status_code")
    if status_code != 0 or fatal_ids:
        raise RuntimeError(
            f"取消收藏失败：status_code={status_code} fatal_ids={fatal_ids} "
            f"message={data.get('status_msg') or data.get('message') or ''}"
        )
    return data


def cancel_collect_single(cookie_header: str, aweme_id: str) -> dict:
    """通过收藏切换接口取消单个视频（action=0, aweme_type=107）。"""
    url = constants.CANCEL_COLLECT_SINGLE_URL + "?" + urlencode(_QUERY_PARAMS)
    params = {"action": 0, "aweme_id": aweme_id, "aweme_type": 107}
    logger.info("cancel_collect_single 请求：url=%s params=%s", url, params)
    response = requests.post(
        url,
        data=urlencode(params),
        headers={**_HEADERS, "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") != 0 or data.get("collects_flag") is not False:
        raise RuntimeError(
            f"单视频取消收藏失败：status_code={data.get('status_code')} "
            f"collects_flag={data.get('collects_flag')} "
            f"message={data.get('status_msg') or data.get('message') or ''}"
        )
    return data


def digg_item(cookie_header: str, aweme_id: str) -> dict:
    """点赞单个视频（POST /aweme/v1/web/commit/item/digg/，type=0 即点赞）。

    ⚠️ 2026-09 实测：抖音写接口（digg/cancel digg/cancel collect）已启用 JS 签名强校验
    （a_bogus / bd-ticket-guard），curl_cffi 直连无论何种 cookie/指纹组合一律返回
    status_code=8"用户未登录"（读接口不受影响）。直连版仅作保留，生产请用
    digg_item_via_browser / cancel_digg_multi_via_browser。
    """
    url = constants.DIGG_URL + "?" + urlencode(_QUERY_PARAMS)
    params = {"aweme_id": aweme_id, "item_type": 0, "type": 0}
    logger.info("digg_item 请求：url=%s params=%s", url, params)
    response = requests.post(
        url,
        data=urlencode(params),
        headers={**_HEADERS, "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") != 0:
        raise RuntimeError(
            f"点赞失败：status_code={data.get('status_code')} "
            f"message={data.get('status_msg') or data.get('message') or ''}"
        )
    return data


def cancel_digg_page(cookie_header: str, aweme_ids: list[str]) -> dict:
    """批量取消点赞单批（POST /aweme/v1/web/cancel/item/digg/multi/）。

    ⚠️ 同 digg_item：直连被 JS 签名校验拦截，仅作保留，生产用
    cancel_digg_multi_via_browser。
    """
    type_map = {aid: 0 for aid in aweme_ids}
    body = urlencode({"aweme_ids": ",".join(aweme_ids)}) + "&" + urlencode(
        {"item_type_map": json.dumps(type_map, separators=(",", ":"))}
    )
    url = constants.CANCEL_DIGG_MULTI_URL + "?" + urlencode(_QUERY_PARAMS)
    logger.info("cancel_digg_page 请求：url=%s params=%s", url, body)
    response = requests.post(
        url, data=body, headers={**_HEADERS, "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    fatal_ids = data.get("fatal_item_ids") or data.get("fatal_ids") or []
    status_code = data.get("status_code")
    if status_code != 0 or fatal_ids:
        raise RuntimeError(
            f"取消点赞失败：status_code={status_code} fatal_ids={fatal_ids} "
            f"message={data.get('status_msg') or data.get('message') or ''}"
        )
    return data


def fetch_like_page(cookie_header: str, sec_user_id: str, max_cursor: int = 0,
                    count: int = 18) -> dict:
    """拉取一页喜欢(点赞)列表（GET /aweme/v1/web/aweme/favorite/，同步阻塞）。

    max_cursor 为上一页响应返回的游标（首页传 0）；
    返回 parse_like_list 的结果 {items, cursor, has_more, total}。
    """
    params = {
        **_QUERY_PARAMS,
        "sec_user_id": sec_user_id,
        "max_cursor": max_cursor,
        "min_cursor": 0,
        "whale_cut_token": "",
        "cut_version": 1,
        "count": count,
    }
    url = constants.LIKE_LIST_URL + "?" + urlencode(params)
    logger.info("fetch_like_page 请求：url=%s", url)
    response = requests.get(
        url,
        headers={**_HEADERS, "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") != 0:
        raise RuntimeError(f"favorite 返回错误 status_code={data.get('status_code')}")
    return parse_like_list(data)


async def fetch_like(cookie_header: str, sec_user_id: str, count: int, on_batch=None):
    """按 max_cursor 游标翻页拉取喜欢(点赞)列表，直到取满 count（0=全部）或 has_more=false。

    返回 (全部 items, 最后一批的 has_more)。
    """
    cursor = 0
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(
            fetch_like_page, cookie_header, sec_user_id, cursor, constants.API_PAGE_COUNT
        )
        page += 1
        collected.extend(batch["items"])
        logger.info(
            "like 第 %d 页：%d 条，累计 %d，has_more=%s",
            page, len(batch["items"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"] or not batch["cursor"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        cursor = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


def fetch_history_page(cookie_header: str, max_cursor: int = 0, count: int = 20) -> dict:
    """拉取一页观看历史（GET /aweme/v1/web/history/read/，同步阻塞）。

    max_cursor 为上一页响应返回的游标（首页传 0）；
    强校验接口：登录会话被踢时返回 status_code=8（响应结构与 favorite 同构）。
    """
    params = {**_QUERY_PARAMS, "max_cursor": max_cursor, "count": count}
    url = constants.HISTORY_URL + "?" + urlencode(params)
    logger.info("fetch_history_page 请求：url=%s", url)
    response = requests.get(
        url,
        headers={**_HEADERS, "cookie": cookie_header,
                 "referer": "https://www.douyin.com/user/self?from_tab_name=main&showTab=record"},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") != 0:
        raise RuntimeError(
            f"history 返回错误 status_code={data.get('status_code')} "
            f"message={data.get('status_msg') or ''}"
        )
    return parse_history(data)


def fetch_watchlater_page(cookie_header: str, offset: int = 0) -> dict:
    """拉取一页稍后再看（GET /aweme/v1/web/watchlater/list/，同步阻塞）。

    分页用 offset 偏移量（浏览器不带 count 参数，服务端单页 20 条）。
    """
    params = {**_QUERY_PARAMS, "offset": offset, "list_type": 0, "operate_type": 0}
    url = constants.WATCHLATER_URL + "?" + urlencode(params)
    logger.info("fetch_watchlater_page 请求：url=%s", url)
    response = requests.get(
        url,
        headers={**_HEADERS, "cookie": cookie_header,
                 "referer": "https://www.douyin.com/user/self?from_tab_name=main&showTab=watch_later"},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") != 0:
        raise RuntimeError(
            f"watchlater 返回错误 status_code={data.get('status_code')} "
            f"message={data.get('status_msg') or ''}"
        )
    return parse_watchlater(data)


async def fetch_history(cookie_header: str, count: int, on_batch=None):
    """按 max_cursor 游标翻页拉取观看历史，直到取满 count（0=全部）或 has_more=false。"""
    cursor = 0
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(
            fetch_history_page, cookie_header, cursor, constants.API_PAGE_COUNT
        )
        page += 1
        collected.extend(batch["items"])
        logger.info(
            "history 第 %d 页：%d 条，累计 %d，has_more=%s",
            page, len(batch["items"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        cursor = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


async def fetch_watchlater(cookie_header: str, count: int, on_batch=None):
    """按 offset 偏移翻页拉取稍后再看，直到取满 count（0=全部）或 has_more=false。"""
    offset = 0
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(fetch_watchlater_page, cookie_header, offset)
        page += 1
        collected.extend(batch["items"])
        logger.info(
            "watchlater 第 %d 页：%d 条，累计 %d，has_more=%s",
            page, len(batch["items"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        offset = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


# 浏览器页面 fetch：抖音写接口有 JS 签名强校验（a_bogus / bd-ticket-guard），
# 页面上下文的 fetch 会被站点 SDK hook 自动加签，是写操作唯一可行通道。
_PAGE_FETCH_JS = """async (payload) => {
    const r = await fetch(payload.path, {
        method: payload.method,
        headers: {'content-type': 'application/x-www-form-urlencoded;charset=UTF-8'},
        body: payload.body,
        credentials: 'include',
    });
    return await r.json();
}"""


async def _open_api_page(ctx):
    """打开喜欢页并等待签名 SDK hook 初始化，返回可发签名请求的 page。

    先调 profile/self 校验页面登录态：会话被其他端登录踢掉时所有写接口都会
    报"用户未登录"，这里提前转为明确的 LoginExpiredError。
    """
    page = await ctx.new_page()
    await page.goto(
        "https://www.douyin.com/user/self?showTab=like",
        wait_until="domcontentloaded", timeout=60000,
    )
    await page.wait_for_timeout(6000)
    data = await page.evaluate(_PAGE_FETCH_JS, {
        "path": "/aweme/v1/web/user/profile/self/?" + urlencode(_QUERY_PARAMS),
        "method": "GET", "body": None,
    })
    if data.get("status_code") != 0:
        await page.close()
        raise LoginExpiredError("抖音登录态失效（页面会话未登录），请重新扫码登录")
    return page


async def _page_fetch(page, path: str, method: str, body: str | None) -> dict:
    """页面上下文发一条 API 请求，status_code != 0 抛 RuntimeError。"""
    data = await page.evaluate(_PAGE_FETCH_JS, {"path": path, "method": method, "body": body})
    status_code = data.get("status_code")
    if status_code != 0:
        raise RuntimeError(
            f"页面请求失败：status_code={status_code} "
            f"message={data.get('status_msg') or data.get('message') or ''}"
        )
    return data


async def digg_item_via_browser(profile_path: str, aweme_id: str) -> dict:
    """点赞单个视频（浏览器页面 fetch，成功响应含 is_digg=1）。"""
    async with browser.session(profile_path, headless=True) as ctx:
        page = await _open_api_page(ctx)
        try:
            body = urlencode({"aweme_id": aweme_id, "item_type": 0, "type": 0})
            return await _page_fetch(
                page, constants.DIGG_URL_PATH + "?" + urlencode(_QUERY_PARAMS), "POST", body)
        finally:
            await page.close()


async def cancel_digg_multi_via_browser(profile_path: str, aweme_ids: list[str],
                                        on_progress=None) -> dict:
    """批量取消点赞：单浏览器会话内按 CANCEL_DIGG_BATCH 分批页面 fetch。

    status_code=5（参数不合法）时对半拆分重试（与取消收藏同策略）。
    返回 {total, batches, canceled}；on_progress 逐批回调
    {"batch_no", "total_batches", "done", "ids"}。
    """
    async def _cancel_chunk(page, ids) -> int:
        try:
            body = urlencode({"aweme_ids": ",".join(ids)}) + "&" + urlencode(
                {"item_type_map": json.dumps({aid: 0 for aid in ids}, separators=(",", ":"))}
            )
            await _page_fetch(
                page, constants.CANCEL_DIGG_MULTI_URL_PATH + "?" + urlencode(_QUERY_PARAMS),
                "POST", body)
            return len(ids)
        except RuntimeError as exc:
            if "status_code=5" not in str(exc):
                raise
            if len(ids) <= 1:
                logger.warning("跳过参数不合法的点赞 ID：%s", ids[0])
                return 0
            midpoint = len(ids) // 2
            logger.warning("取消点赞批次参数不合法，拆分为 %d/%d 条继续处理",
                           midpoint, len(ids) - midpoint)
            left = await _cancel_chunk(page, ids[:midpoint])
            right = await _cancel_chunk(page, ids[midpoint:])
            return left + right

    batches = [aweme_ids[i: i + constants.CANCEL_DIGG_BATCH]
               for i in range(0, len(aweme_ids), constants.CANCEL_DIGG_BATCH)]
    canceled_total = 0
    async with browser.session(profile_path, headless=True) as ctx:
        page = await _open_api_page(ctx)
        try:
            for i, chunk in enumerate(batches, start=1):
                canceled_total += await _cancel_chunk(page, chunk)
                logger.info("cancel_digg 第 %d/%d 批：%d 条", i, len(batches), len(chunk))
                if on_progress:
                    await on_progress({
                        "batch_no": i, "total_batches": len(batches),
                        "done": canceled_total, "ids": chunk,
                    })
                if i < len(batches):
                    await asyncio.sleep(constants.CANCEL_DIGG_INTERVAL_SEC)
        finally:
            await page.close()
    return {"total": len(aweme_ids), "batches": len(batches), "canceled": canceled_total}


async def _cancel_collect_batch_with_retry(cookie_header: str, aweme_ids: list[str]) -> int:
    """取消一批收藏；status_code=5 时退避重试，避免风控瞬时失败中断整项任务。"""
    # 抖音对小于整批的请求偶发返回成功但实际不生效，逐 ID 请求可避免该情况。
    if len(aweme_ids) < constants.CANCEL_COLLECT_BATCH:
        logger.info("取消收藏小批次改为逐条处理：%d 条", len(aweme_ids))
        total = 0
        for aweme_id in aweme_ids:
            total += await _cancel_collect_single_with_retry(cookie_header, aweme_id)
        return total
    for attempt in range(1, constants.CANCEL_COLLECT_RETRIES + 1):
        try:
            await asyncio.to_thread(cancel_collect_page, cookie_header, aweme_ids)
            return len(aweme_ids)
        except RuntimeError as exc:
            error_text = str(exc)
            if "status_code=5" in error_text and "参数不合法" in error_text:
                if len(aweme_ids) <= 1:
                    logger.warning("跳过参数不合法的收藏 ID：%s", aweme_ids[0])
                    return 0
                midpoint = len(aweme_ids) // 2
                logger.warning(
                    "取消收藏批次参数不合法，拆分为 %d/%d 条继续处理",
                    midpoint, len(aweme_ids) - midpoint,
                )
                left = await _cancel_collect_batch_with_retry(cookie_header, aweme_ids[:midpoint])
                right = await _cancel_collect_batch_with_retry(cookie_header, aweme_ids[midpoint:])
                return left + right
            if "status_code=5" not in error_text or attempt >= constants.CANCEL_COLLECT_RETRIES:
                raise
            delay = constants.CANCEL_COLLECT_INTERVAL_SEC * (2 ** attempt)
            logger.warning(
                "取消收藏批次遇到 status_code=5，第 %d/%d 次重试，%d 条，等待 %.1fs：%s",
                attempt, constants.CANCEL_COLLECT_RETRIES, len(aweme_ids), delay, exc,
            )
            await asyncio.sleep(delay)


async def _cancel_collect_single_with_retry(cookie_header: str, aweme_id: str) -> int:
    for attempt in range(1, constants.CANCEL_COLLECT_RETRIES + 1):
        try:
            await asyncio.to_thread(cancel_collect_single, cookie_header, aweme_id)
            return 1
        except RuntimeError as exc:
            if "status_code=5" in str(exc) and "参数不合法" in str(exc):
                logger.warning("跳过参数不合法的收藏 ID：%s", aweme_id)
                return 0
            if attempt >= constants.CANCEL_COLLECT_RETRIES or "status_code=5" not in str(exc):
                raise
            await asyncio.sleep(constants.CANCEL_COLLECT_INTERVAL_SEC * (2 ** attempt))


async def cancel_collect_by_window(cookie_header: str, dt_from, dt_to, on_progress=None,
                                    time_mode: str = "collected") -> dict:
    """完整扫描收藏列表，按视频上传时间（parser 的 collected_at）过滤并取消。

    抖音收藏列表接口不提供真实的加入收藏时间，不能使用分页 cursor 提前停止；
    必须遍历到接口结束，再用条目中的 collected_at（当前由视频 create_time 填充）
    匹配日期区间。time_mode 保留用于兼容旧请求，两种模式都使用该条目时间。
    """
    from app.utils import filter_by_date_window

    server_cursor = 0
    canceled_total = 0
    matched_ids: list[str] = []
    matched_seen: set[str] = set()
    total_fetched = 0
    page = 0
    while True:
        batch = await asyncio.to_thread(
            fetch_listcollection_page, cookie_header, server_cursor, constants.API_PAGE_COUNT
        )
        page += 1
        items = batch["items"]
        total_fetched += len(items)
        page_lo = _cursor_time(batch["cursor"])
        matched = filter_by_date_window(items, dt_from, dt_to)
        ids = [it["content_id"] for it in matched if it.get("content_id")]
        for content_id in ids:
            if content_id not in matched_seen:
                matched_seen.add(content_id)
                matched_ids.append(content_id)

        if on_progress:
            await on_progress({
                "type": "progress",
                "page": page,
                "oldest_collected_at": page_lo.isoformat(timespec="seconds") if page_lo else None,
                "matched_this_page": len(ids),
                "canceled": canceled_total,
                "total_fetched": total_fetched,
            })

        if not batch["has_more"]:
            break
        if not batch["cursor"]:
            raise RuntimeError("收藏分页中断：接口仍有更多数据但未返回 cursor")
        server_cursor = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)

    # 必须等收藏列表完整扫描结束后再删除，避免删除当前页改变 cursor 导致漏扫。
    # 扫描完成后按较小批次取消，降低接口返回“参数不合法”的概率。
    for i in range(0, len(matched_ids), constants.CANCEL_COLLECT_BATCH):
        chunk = matched_ids[i:i + constants.CANCEL_COLLECT_BATCH]
        canceled_total += await _cancel_collect_batch_with_retry(cookie_header, chunk)
        logger.info("cancel_collect 扫描完成后取消第 %d 批：%d 条（累计 %d）",
                    i // constants.CANCEL_COLLECT_BATCH + 1, len(chunk), canceled_total)
        if on_progress:
            await on_progress({
                "type": "progress",
                "page": page,
                "oldest_collected_at": page_lo.isoformat(timespec="seconds") if page_lo else None,
                "matched_this_page": 0,
                "canceled": canceled_total,
                "total_fetched": total_fetched,
            })
        if i + constants.CANCEL_COLLECT_BATCH < len(matched_ids):
            await asyncio.sleep(constants.CANCEL_COLLECT_INTERVAL_SEC)

    return {
        "matched": len(matched_ids),
        "canceled": canceled_total,
        "pages": page,
        "stopped_early": False,
        "total_fetched": total_fetched,
        "time_mode": time_mode,
    }


async def cancel_collect_multi(cookie_header: str, aweme_ids: list[str], on_progress=None) -> dict:
    """批量取消收藏：按 CANCEL_COLLECT_BATCH 分批执行。

    返回 {total, batches, canceled}；on_progress(info: dict) 逐批回调进度：
    {"batch_no", "total_batches", "done", "ids"}（done 为累计取消条数）。
    """
    batches = [aweme_ids[i: i + constants.CANCEL_COLLECT_BATCH]
               for i in range(0, len(aweme_ids), constants.CANCEL_COLLECT_BATCH)]
    canceled_total = 0
    for i, chunk in enumerate(batches, start=1):
        canceled = await _cancel_collect_batch_with_retry(cookie_header, chunk)
        canceled_total += canceled
        logger.info("cancel_collect 第 %d/%d 批：%d 条", i, len(batches), len(chunk))
        if on_progress:
            await on_progress({
                "batch_no": i, "total_batches": len(batches), "done": canceled_total, "ids": chunk,
            })
        if i < len(batches):
            await asyncio.sleep(constants.CANCEL_COLLECT_INTERVAL_SEC)
    return {"total": len(aweme_ids), "batches": len(batches), "canceled": canceled_total}
