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
    ApiOperation,
    ApiOperationParam,
    BasePlatformAdapter,
    FetchResult,
    LoginExpiredError,
)
from app.services import browser
from . import api_client
from . import constants
from .parser import parse_embedded_saved, parse_saved_media

logger = logging.getLogger("favapi.threads")


def _split_ids(raw: str) -> list[str]:
    """把换行/逗号分隔的 ID 文本拆成去空列表。"""
    import re

    return [t.strip() for t in re.split(r"[\s,，;；]+", raw or "") if t.strip()]


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
    api_operations = (
        ApiOperation(
            op_id="save_post",
            name="收藏帖子",
            description="API 直连收藏指定帖子（帖子详情页「收藏」同款接口）",
            params=(
                ApiOperationParam(
                    key="media_id", label="帖子 ID", type="text", required=True,
                    placeholder="例如：3987468812979200688",
                    help="纯数字帖子 pk，可从收藏列表条目的 content_id 获取",
                ),
            ),
        ),
        ApiOperation(
            op_id="cancel_saved_multi",
            name="批量取消收藏",
            description="按帖子 ID 列表批量取消收藏（操作不可恢复）",
            danger=True,
            params=(
                ApiOperationParam(
                    key="post_ids", label="帖子 ID 列表", type="textarea", required=True,
                    placeholder="ID 之间用逗号或换行分隔，例如：\n3987260322440819856\n3987010911676295522",
                    help="纯数字帖子 pk（收藏列表条目的 content_id）",
                ),
            ),
        ),
    )

    def __init__(self, base_dir=None):
        self.base_dir = base_dir  # 图标目录（/platforms/{id}/icon 下发用）

    async def execute_api_operation(
        self, op_id: str, account: AccountContext, params: dict, on_event=None
    ) -> dict:
        if op_id == "save_post":
            return await self._op_save_post(account, params)
        if op_id == "cancel_saved_multi":
            return await self._op_cancel_saved(account, params, on_event)
        raise ValueError(f"未知操作：{op_id}")

    async def _op_save_post(self, account: AccountContext, params: dict) -> dict:
        """收藏指定帖子（save mutation）。"""
        media_id = str((params or {}).get("media_id") or "").strip()
        if not media_id.isdigit():
            raise ValueError("请填写要收藏的帖子 ID（纯数字 pk）")
        logger.info("[%s] API 操作 save_post：%s", account.account_id, media_id)
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        lsd = await asyncio.to_thread(api_client.fetch_lsd, cookie_header)
        media = await asyncio.to_thread(
            api_client.save_media, cookie_header, lsd, media_id)
        logger.info("[%s] 收藏完成：has_viewer_saved=%s", account.account_id,
                    media.get("has_viewer_saved"))
        return {"media_id": media_id, "has_viewer_saved": media.get("has_viewer_saved")}

    async def _op_cancel_saved(self, account: AccountContext, params: dict, on_event=None) -> dict:
        """批量取消收藏（unsave mutation 逐条执行）。"""
        media_ids = _split_ids(str((params or {}).get("post_ids") or ""))
        if not media_ids:
            raise ValueError("请填写要取消收藏的帖子 ID 列表")
        if any(not t.isdigit() for t in media_ids):
            raise ValueError("post_ids 含非数字 ID，请检查输入")

        async def _progress(info: dict):
            if on_event:
                await on_event({"type": "progress", **info})

        logger.info("[%s] API 操作 cancel_saved_multi：%d 条", account.account_id, len(media_ids))
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        result = await api_client.unsave_multi(
            cookie_header, media_ids, on_progress=_progress)
        result["matched"] = len(media_ids)
        logger.info("[%s] 批量取消收藏完成：%s", account.account_id, result)
        return result

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
        """登录态检查：cookie 快速判定 + API 真实校验。

        cookie 缺失直接 False；cookie 存在但服务端会话已被踢（sessionid 失效）
        由 fetch_viewer_profile 判定。网络异常向上抛（路由层 503），不误标 expired。
        """
        logged_in, _ = await self._check_and_maybe_refresh(account, refresh=False)
        return logged_in

    async def check_login_status_and_refresh(self, account: AccountContext) -> tuple[bool, bool]:
        """单会话版本：一次读 cookie + 一次 API 校验，登录有效时身份已随响应拿到，直接回填。"""
        return await self._check_and_maybe_refresh(account, refresh=True)

    async def _check_and_maybe_refresh(self, account: AccountContext, refresh: bool) -> tuple[bool, bool]:
        async with browser.session(
            account.profile_path, headless=True, proxy=api_client.resolve_proxy()
        ) as ctx:
            cookies = await ctx.cookies(urls=[constants.FAVORITES_URL])
        if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
            logger.info("[%s] 登录态检查：无效（profile 无登录 cookie）", account.account_id)
            return False, False
        cookie_header = "; ".join(
            f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
        try:
            profile = await asyncio.to_thread(
                api_client.fetch_viewer_profile, cookie_header)
        except LoginExpiredError:
            logger.warning("[%s] 登录态检查：cookie 存在但服务端会话已失效", account.account_id)
            return False, False
        logger.info("[%s] 登录态检查：有效（@%s）", account.account_id, profile.get("username"))
        if not refresh:
            return True, False
        try:
            await self._save_owner(account, profile)
            return True, True
        except Exception:
            logger.warning("[%s] 身份回填失败（不影响登录态结论）", account.account_id, exc_info=True)
            return True, False

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：extra.threads.owner = {id, username, avatar}。"""
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        profile = await asyncio.to_thread(api_client.fetch_viewer_profile, cookie_header)
        await self._save_owner(account, profile)

    async def _save_owner(self, account: AccountContext, profile: dict) -> None:
        from app.services import account_manager  # 延迟导入避免循环依赖

        owner = {
            "id": profile["id"],
            "username": profile.get("username"),
            "avatar": profile.get("avatar"),  # 带签名 CDN 原链，save_owner 落盘防过期
        }
        saved = await account_manager.save_owner(account.account_id, "threads", {"owner": owner})
        if saved is not None:
            logger.info("[%s] 身份信息已回填：@%s(%s)",
                        account.account_id, profile.get("username"), profile["id"])

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
