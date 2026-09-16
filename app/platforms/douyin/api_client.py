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
    统一走 browser.session()：channel/并发上限/同 profile 串行锁一处维护，
    避免与抓取会话同时打开同一 profile。
    """
    async with browser.session(profile_path, headless=True) as ctx:
        cookies = await ctx.cookies()
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("抖音登录态缺失（profile 无 sessionid），请重新扫码登录")
    return header


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
    # 扫描完成后按接口上限分批取消；当前接口单次最多 100 条。
    for i in range(0, len(matched_ids), constants.CANCEL_COLLECT_BATCH):
        chunk = matched_ids[i:i + constants.CANCEL_COLLECT_BATCH]
        await asyncio.to_thread(cancel_collect_page, cookie_header, chunk)
        canceled_total += len(chunk)
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
