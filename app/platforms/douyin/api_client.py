"""抖音收藏列表 API 直连客户端。

抖音按客户端 TLS/HTTP2 指纹拦截非浏览器请求（node/Go/原生 httpx 均返回空响应），
这里用 curl-impersonate（curl_cffi impersonate="chrome"）完整模拟 Chrome 指纹直连
`POST /aweme/v1/web/aweme/listcollection/`，比浏览器滚动 + 响应拦截快一个量级。

登录态复用账号的浏览器 profile：起一次无头 Chromium 读出 cookies 后关闭，
后续翻页全部走纯 HTTP。
"""
import asyncio
import json
import logging
import pathlib
from urllib.parse import urlencode

from curl_cffi import requests

from app.services import browser
from . import constants
from .parser import parse_listcollection
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
    用同步 playwright 在工作线程读：uvicorn 在 Windows 上的事件循环不支持子进程，
    async_playwright 起不来；sync API 在线程内自建 Proactor 循环不受影响。
    """
    cookies = await asyncio.to_thread(_read_cookies_sync, profile_path)
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("抖音登录态缺失（profile 无 sessionid），请重新扫码登录")
    return header


def _read_cookies_sync(profile_path: str) -> list[dict]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(pathlib.Path(profile_path)),
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            return ctx.cookies()
        finally:
            ctx.close()


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


async def fetch_listcollection(cookie_header: str, cursor: int, count: int, on_batch=None,
                               stop_before: "object | None" = None):
    """按服务端游标翻页直到取满 count（0=全部）或 has_more=false。

    stop_before（aware datetime）：收藏按时间倒序，当某页条目全部有 collected_at
    且最旧一条已早于 stop_before 时提前终止（后续页更旧不可能命中），日期区间场景用。
    返回 (全部 items, 最后一批的 has_more)。
    """
    from datetime import datetime as _dt

    from app.utils import item_collected_time

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
        if stop_before is not None and batch["items"]:
            times = [item_collected_time(it) for it in batch["items"]]
            # 全页时间可解析且最旧一条早于下界 → 后续页更旧，提前终止
            if all(t is not None for t in times) and min(times) < stop_before:
                logger.info("listcollection 第 %d 页最旧条目早于下界，提前终止", page)
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
    response = requests.post(
        url, data=body, headers={**_HEADERS, "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    fatal_ids = data.get("fatal_ids") or []
    if data.get("status_code") != 0 or fatal_ids:
        raise RuntimeError(
            f"取消收藏失败：status_code={data.get('status_code')} fatal_ids={fatal_ids}"
        )
    return data


async def cancel_collect_by_window(cookie_header: str, dt_from, dt_to, on_progress=None) -> dict:
    """按收藏日期区间边拉边取消：每页拉取 → 过滤 [from, to] → 命中当页立即取消 → 上报进度。

    收藏按时间倒序，整页最旧一条早于 dt_from 时提前终止（后续不可能命中）。
    on_progress(info) 每页回调：{"page", "oldest_collected_at", "matched_this_page",
    "canceled", "total_fetched"}，其中 oldest_collected_at 为当前翻到的最早收藏时间。
    """
    from app.utils import filter_by_date_window, item_collected_time

    server_cursor = 0
    canceled_total = 0
    total_fetched = 0
    page = 0
    stop_early = False
    while True:
        batch = await asyncio.to_thread(
            fetch_listcollection_page, cookie_header, server_cursor, constants.API_PAGE_COUNT
        )
        page += 1
        items = batch["items"]
        total_fetched += len(items)
        times = [item_collected_time(it) for it in items]
        oldest = min((t for t in times if t is not None), default=None)

        matched = filter_by_date_window(items, dt_from, dt_to)
        ids = [it["content_id"] for it in matched if it.get("content_id")]
        if ids:
            await asyncio.to_thread(cancel_collect_page, cookie_header, ids)
            canceled_total += len(ids)
            logger.info("cancel_collect 第 %d 页命中 %d 条已取消（累计 %d）",
                        page, len(ids), canceled_total)

        if on_progress:
            await on_progress({
                "type": "progress",
                "page": page,
                "oldest_collected_at": oldest.isoformat(timespec="seconds") if oldest else None,
                "matched_this_page": len(ids),
                "canceled": canceled_total,
                "total_fetched": total_fetched,
            })

        if not batch["has_more"] or not batch["cursor"]:
            break
        if dt_from is not None and items and all(t is not None for t in times) and oldest < dt_from:
            stop_early = True
            logger.info("cancel_collect 第 %d 页最旧条目早于下界，提前终止", page)
            break
        server_cursor = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)

    return {
        "matched": canceled_total,
        "canceled": canceled_total,
        "pages": page,
        "stopped_early": stop_early,
        "total_fetched": total_fetched,
    }


async def cancel_collect_multi(cookie_header: str, aweme_ids: list[str], on_progress=None) -> dict:
    """批量取消收藏：按 CANCEL_COLLECT_BATCH 分批执行。

    返回 {total, batches, canceled}；on_progress(info: dict) 逐批回调进度：
    {"batch_no", "total_batches", "done", "ids"}（done 为累计取消条数）。
    """
    batches = [aweme_ids[i: i + constants.CANCEL_COLLECT_BATCH]
               for i in range(0, len(aweme_ids), constants.CANCEL_COLLECT_BATCH)]
    for i, chunk in enumerate(batches, start=1):
        await asyncio.to_thread(cancel_collect_page, cookie_header, chunk)
        done = min(i * constants.CANCEL_COLLECT_BATCH, len(aweme_ids))
        logger.info("cancel_collect 第 %d/%d 批：%d 条", i, len(batches), len(chunk))
        if on_progress:
            await on_progress({
                "batch_no": i, "total_batches": len(batches), "done": done, "ids": chunk,
            })
        if i < len(batches):
            await asyncio.sleep(constants.CANCEL_COLLECT_INTERVAL_SEC)
    return {"total": len(aweme_ids), "batches": len(batches), "canceled": len(aweme_ids)}
