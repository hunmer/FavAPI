"""Threads 适配器：登录 / 登录态检查 / 收藏（已保存）列表抓取。

两种执行方式：
- API 直连（params.method="api"）：profile cookies + curl_cffi 直连 GraphQL，快且不占浏览器；
- 浏览器模拟（默认）：打开 /saved 拦截 GraphQL 响应 + 滚动加载。
  首屏数据嵌在页面 HTML 的 Relay preloader 里（无独立 XHR），从导航响应正文提取，
  修复了原声明式实现漏抓首页的问题。

代理：threads.com 在部分网络不可直达，沿用声明式平台的 auto 解析
（env → Windows 注册表），浏览器会话与直连共用。
"""
import asyncio
import logging
import time

from app import config
from app.platforms.base import (
    AccountContext,
    BasePlatformAdapter,
    FetchResult,
    LoginExpiredError,
)
from app.services import browser
from . import api_client
from . import constants
from .parser import parse_embedded_saved, parse_saved_media

logger = logging.getLogger("favapi.threads")


def _merge_items(batches: list[dict]) -> list[dict]:
    """多批响应按 content_id 去重合并（保持首次出现顺序）。"""
    seen: dict[str, dict] = {}
    for batch in batches:
        for item in batch["items"]:
            seen.setdefault(item["content_id"], item)
    return list(seen.values())


class ThreadsAdapter(BasePlatformAdapter):
    platform = constants.PLATFORM
    display_name = constants.DISPLAY_NAME
    home_url = constants.HOME_URL
    icon = "favicon.ico"
    implemented = True
    supported_actions = ("list_favorites",)
    api_fetch_implemented = True  # 收藏列表支持 API 直连（params.method="api"）

    def __init__(self, base_dir=None):
        self.base_dir = base_dir  # 图标目录（/platforms/{id}/icon 下发用）

    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        """打开有头浏览器等待用户登录；检测到 sessionid 即成功。"""
        timeout = timeout or config.LOGIN_TIMEOUT
        deadline = time.monotonic() + timeout
        logger.info("[%s] 打开登录窗口，等待登录（最长 %ss）", account.account_id, timeout)
        async with browser.session(
            account.profile_path, headless=False, proxy=api_client.resolve_proxy()
        ) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(constants.HOME_URL, wait_until="domcontentloaded")
            checked = 0
            while time.monotonic() < deadline:
                cookies = await ctx.cookies()
                checked += 1
                if browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
                    logger.info("[%s] 第 %d 次轮询检测到登录 cookie，登录成功",
                                account.account_id, checked)
                    return True
                await asyncio.sleep(3)
            logger.warning("[%s] 等待登录超时（%ss，共轮询 %d 次），登录未完成",
                           account.account_id, timeout, checked)
            return False

    async def check_login_status(self, account: AccountContext) -> bool:
        """登录态检查：仅读取 profile cookie，不导航页面 → 固定无头。"""
        async with browser.session(
            account.profile_path, headless=True, proxy=api_client.resolve_proxy()
        ) as ctx:
            cookies = await ctx.cookies()
            ok = browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS)
            logger.info("[%s] 登录态检查：%s", account.account_id, "有效" if ok else "无效")
            return ok

    async def fetch_favorites(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        if self.resolve_fetch_method(params) == "api":
            return await self.fetch_favorites_api(account, params, on_batch)
        return await self._fetch_favorites_browser(account, params, on_batch)

    async def fetch_favorites_api(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        """API 直连：profile cookies + curl-impersonate Chrome 指纹 POST GraphQL。

        cursor 语义与浏览器模式一致（已抓取条数偏移）；接口翻页内部用 end_cursor。
        """
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        logger.info("[%s] API 直连抓取收藏：count=%s cursor=%d",
                    account.account_id, count or "全部", skip)

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        collected, last_has_more = await api_client.fetch_saved(
            cookie_header, count=(count + skip) if count else 0, on_batch=on_batch
        )
        window = collected[skip:] if not count else collected[skip: skip + count]
        logger.info("[%s] API 直连抓取完成：共 %d 条，返回 [%d:%d] %d 条",
                    account.account_id, len(collected), skip, skip + len(window), len(window))
        return FetchResult(
            items=window,
            cursor=skip + len(window),
            has_more=last_has_more and (not count or len(collected) >= skip + count),
            total=len(collected),
        )

    async def _fetch_favorites_browser(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        """浏览器模拟：首屏从 /saved HTML 的 Relay preloader 提取，滚动触发翻页 XHR 拦截。"""
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        logger.info("[%s] 开始抓取收藏：count=%s cursor=%d",
                    account.account_id, count or "全部", skip)

        batches: list[dict] = []

        async def _feed(parsed: dict, label: str) -> None:
            if not parsed or not parsed["items"]:
                return
            batches.append(parsed)
            logger.info("捕获 %s 批次 #%d：%d 条，has_more=%s",
                        label, len(batches), len(parsed["items"]), parsed["has_more"])
            if on_batch:
                await on_batch({"page": len(batches), "items": parsed["items"]})

        async def _on_response(response):
            url = response.url
            if url.rstrip("/") == constants.FAVORITES_URL.rstrip("/"):
                # 导航响应正文：内嵌首屏 Relay preloader（无独立 XHR）
                try:
                    html = await response.text()
                except Exception as exc:
                    logger.warning("读取收藏页正文失败：%s", exc)
                    return
                await _feed(parse_embedded_saved(html), "preloader")
            elif "/graphql/query" in url and constants.SAVED_DOC_ID in (
                response.request.post_data or ""
            ):
                try:
                    data = await response.json()
                except Exception as exc:
                    logger.warning("GraphQL 响应解析失败：%s", exc)
                    return
                await _feed(parse_saved_media(data), "graphql")

        async with browser.session(
            account.profile_path, headless=config.HEADLESS, proxy=api_client.resolve_proxy()
        ) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            page.on("response", _on_response)
            await page.goto(constants.FAVORITES_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(constants.WAIT_AFTER_GOTO_MS)

            cookies = await ctx.cookies()
            if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
                raise LoginExpiredError("Threads 登录态缺失，请重新登录")

            rounds, stall, last_merged = 0, 0, -1
            while rounds < constants.MAX_SCROLL_ROUNDS:
                merged = _merge_items(batches)
                has_more = batches[-1]["has_more"] if batches else True
                if count and len(merged) >= count + skip:
                    logger.info("已收集 %d 条（目标 %d），停止滚动", len(merged), count + skip)
                    break
                if not has_more:
                    logger.info("接口提示没有更多数据（共 %d 条），停止滚动", len(merged))
                    break
                if stall >= constants.MAX_STALL_ROUNDS:
                    logger.warning("连续 %d 轮滚动无新增数据（当前 %d 条），提前结束避免空转",
                                   stall, len(merged))
                    break
                await page.mouse.wheel(0, 2500)
                await page.wait_for_timeout(constants.SCROLL_INTERVAL_MS)
                rounds += 1

                new_merged = _merge_items(batches)
                stall = stall + 1 if len(new_merged) == last_merged else 0
                last_merged = len(new_merged)
                logger.info("第 %d 轮滚动：批次 %d，去重 %d 条", rounds, len(batches), len(new_merged))

            # 等最后一次滚动触发的响应落地
            await page.wait_for_timeout(1200)

        merged = _merge_items(batches)
        window = merged[skip:] if not count else merged[skip: skip + count]
        last_has_more = bool(batches and batches[-1]["has_more"])
        logger.info("[%s] 抓取完成：捕获批次 %d，去重 %d 条，返回 [%d:%d] 共 %d 条，has_more=%s",
                    account.account_id, len(batches), len(merged), skip,
                    skip + len(window), len(window), last_has_more)
        return FetchResult(
            items=window,
            cursor=skip + len(window),
            has_more=last_has_more and (not count or len(merged) >= skip + count),
            total=len(merged),
        )
