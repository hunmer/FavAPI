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
    """按收藏日期区间边拉边取消：每页拉取 → 过滤 [from, to] → 命中当页立即取消 → 上报进度。

    time_mode 两种判定语义（接口不返回条目级收藏时间，只有页级游标）：
    - "collected"（默认，按收藏时间）：页收藏区间 (本页cursor, 上页cursor] 完全落在
      目标区间内 → 整页取消；与目标无交集 → 跳过；边界页 → 条目发布时间兜底近似。
    - "published"（按发布时间）：条目 collected_at（发布时间兜底）逐条判定。

    列表按真实收藏时间倒序，游标早于 dt_from 时提前终止（后续条目收藏/发布时间
    必然更早，两种语义下都不再命中）。
    on_progress(info) 每页回调：{"page", "oldest_collected_at"（已翻到的收藏时间），
    "matched_this_page", "canceled", "total_fetched"}。
    """
    from app.utils import filter_by_date_window

    server_cursor = 0
    canceled_total = 0
    total_fetched = 0
    page = 0
    stop_early = False
    page_hi = None  # 上一页游标时间 = 本页条目收藏时间上界（首页视为 +∞）
    skip_advance = False
    while True:
        batch = await asyncio.to_thread(
            fetch_listcollection_page, cookie_header, server_cursor, constants.API_PAGE_COUNT
        )
        page += 1
        items = batch["items"]
        total_fetched += len(items)
        page_lo = _cursor_time(batch["cursor"])  # 本页条目收藏时间下界（末页无游标视为 -∞）

        if time_mode == "collected":
            # 页区间 (page_lo, page_hi] 与目标 [dt_from, dt_to] 的关系
            no_overlap = (
                (dt_from is not None and page_hi is not None and page_hi < dt_from)
                or (dt_to is not None and page_lo is not None and page_lo > dt_to)
            )
            fully_inside = (
                (page_lo is None or dt_from is None or page_lo >= dt_from)
                and (page_hi is None or dt_to is None or page_hi <= dt_to)
            )
            if no_overlap:
                matched = []
            elif fully_inside:
                matched = items  # 整页收藏时间都在目标内
            else:
                # 跨边界页：收藏稀疏时段一页可能跨越数月，页级判定失效。
                # 从本页起点游标开始逐条精翻（count=1 时游标即该条收藏时间），判定精确。
                sub_cursor = server_cursor
                page_lo = None  # 精翻后更新为本段实际到达的时间
                pending: list[str] = []

                async def _flush():
                    nonlocal canceled_total, pending
                    if pending:
                        await asyncio.to_thread(cancel_collect_page, cookie_header, pending)
                        canceled_total += len(pending)
                        logger.info("cancel_collect 精翻段取消 %d 条（累计 %d）", len(pending), canceled_total)
                        pending = []

                while True:
                    b1 = await asyncio.to_thread(
                        fetch_listcollection_page, cookie_header, sub_cursor, 1
                    )
                    if not b1["items"]:
                        break
                    t1 = _cursor_time(b1["cursor"])
                    if t1 is None:
                        break  # 游标异常，放弃精翻
                    if dt_from is not None and t1 < dt_from:
                        page_lo = t1
                        break  # 越过下界
                    if (dt_from is None or t1 >= dt_from) and (dt_to is None or t1 <= dt_to):
                        cid = b1["items"][0].get("content_id")
                        if cid:
                            pending.append(cid)
                            if len(pending) >= constants.CANCEL_COLLECT_BATCH:
                                await _flush()
                    page_lo = t1
                    if not b1["has_more"] or not b1["cursor"]:
                        break
                    sub_cursor = b1["cursor"]
                    await asyncio.sleep(constants.CANCEL_COLLECT_INTERVAL_SEC)
                await _flush()
                matched = []  # 已在精翻中处理
                items = []    # 精翻已覆盖本页区间，避免主循环重复取消
                if sub_cursor != server_cursor:
                    server_cursor = sub_cursor  # 主循环从精翻到达的位置继续
                    skip_advance = True
        else:
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
                "oldest_collected_at": page_lo.isoformat(timespec="seconds") if page_lo else None,
                "matched_this_page": len(ids),
                "canceled": canceled_total,
                "total_fetched": total_fetched,
            })

        if not batch["has_more"] or not batch["cursor"]:
            break
        if dt_from is not None and page_lo and page_lo < dt_from:
            stop_early = True
            logger.info("cancel_collect 第 %d 页游标(%s)早于下界，提前终止", page, page_lo)
            break
        page_hi = page_lo
        if not skip_advance:
            server_cursor = batch["cursor"]
        skip_advance = False
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)

    return {
        "matched": canceled_total,
        "canceled": canceled_total,
        "pages": page,
        "stopped_early": stop_early,
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
