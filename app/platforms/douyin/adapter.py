"""抖音适配器：扫码登录 / 登录态检查 / 收藏列表抓取（响应拦截 + 滚动加载）。"""
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
from . import constants
from .parser import parse_listcollection

logger = logging.getLogger("favapi.douyin")

# 抖音个人页的滚动发生在内部容器而非 window：找到真正可滚动的容器设置 scrollTop
_SCROLL_JS = """
() => {
  const step = 2500;
  const candidates = Array.from(document.querySelectorAll('div'))
    .filter(el => el.scrollHeight > el.clientHeight + 200 && el.clientHeight > 300);
  const target = candidates.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
  if (target) {
    target.scrollTop += step;
    return {mode: 'container', scrollTop: target.scrollTop, scrollHeight: target.scrollHeight};
  }
  window.scrollBy(0, step);
  return {mode: 'window', scrollTop: window.scrollY, scrollHeight: document.body.scrollHeight};
}
"""


def _merge_batches(batches: list[dict]) -> list[dict]:
    """多批响应按 content_id 去重合并（保持首次出现顺序）。"""
    seen: dict[str, dict] = {}
    for batch in batches:
        for item in batch["items"]:
            seen.setdefault(item["content_id"], item)
    return list(seen.values())


class DouyinAdapter(BasePlatformAdapter):
    platform = constants.PLATFORM
    display_name = constants.DISPLAY_NAME
    home_url = constants.HOME_URL
    implemented = True
    # list_collects / get_collect_videos 为 PRD 预留的后续 action
    supported_actions = ("list_favorites",)

    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        """打开有头浏览器等待扫码；检测到 sessionid 即成功。"""
        timeout = timeout or config.LOGIN_TIMEOUT
        deadline = time.monotonic() + timeout
        logger.info("[%s] 打开登录窗口，等待扫码（最长 %ss）", account.account_id, timeout)
        async with browser.session(account.profile_path, headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(constants.HOME_URL, wait_until="domcontentloaded")
            checked = 0
            while time.monotonic() < deadline:
                cookies = await ctx.cookies()
                checked += 1
                if browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
                    logger.info("[%s] 第 %d 次轮询检测到登录 cookie，登录成功", account.account_id, checked)
                    return True
                await asyncio.sleep(3)
            logger.warning("[%s] 等待扫码超时（%ss，共轮询 %d 次），登录未完成", account.account_id, timeout, checked)
            return False

    async def check_login_status(self, account: AccountContext) -> bool:
        """登录态检查：仅读取 profile cookie，不导航页面 → 固定无头，避免轮询时反复弹出可见窗口。"""
        async with browser.session(account.profile_path, headless=True) as ctx:
            cookies = await ctx.cookies()
            ok = browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS)
            logger.info("[%s] 登录态检查：%s", account.account_id, "有效" if ok else "无效")
            return ok

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：打开个人主页，拦截页面自身的 profile/self 响应。

        该接口带 a_bogus 签名无法直接构造请求，沿用收藏抓取的响应拦截方案。
        """
        import json

        holder: dict = {}
        async with browser.session(account.profile_path, headless=True) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            async def _on_response(response):
                if constants.PROFILE_SELF_API not in response.url:
                    return
                try:
                    data = await response.json()
                except Exception:
                    return
                if data.get("status_code") == 0 and data.get("user"):
                    holder["user"] = data["user"]

            page.on("response", _on_response)
            await page.goto(constants.FAVORITES_URL, wait_until="domcontentloaded")
            for _ in range(15):  # 最多等页面请求落地 15s
                if holder:
                    break
                await page.wait_for_timeout(1000)

        user = holder.get("user")
        if not user:
            logger.info("[%s] 未拦截到 profile/self（可能未登录），跳过身份回填", account.account_id)
            return

        def _avatar(u: dict) -> str | None:
            for key in ("avatar_168x168", "avatar_300x300", "avatar_larger"):
                urls = (u.get(key) or {}).get("url_list") or []
                if urls:
                    return urls[0]
            return None

        owner = {
            "uid": str(user.get("uid") or ""),
            "sec_uid": str(user.get("sec_uid") or ""),
            "short_id": str(user.get("short_id") or ""),
            "nickname": user.get("nickname"),
            "avatar": _avatar(user),  # 带签名 CDN 链接，过期后重新刷新即可
        }
        from app.services import account_manager  # 延迟导入避免循环依赖

        row = await account_manager.get_account(account.account_id)
        if row is None:
            return
        extra = row.get("extra") or {}
        extra["douyin"] = {"owner": owner}
        await account_manager.update_account(
            account.account_id, extra=json.dumps(extra, ensure_ascii=False)
        )
        logger.info("[%s] 身份信息已回填：%s(%s)", account.account_id, owner.get("nickname"), owner["uid"])

    async def fetch_favorites(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        logger.info(
            "[%s] 开始抓取收藏：count=%s cursor=%d", account.account_id, count or "全部", skip
        )

        batches: list[dict] = []
        async with browser.session(account.profile_path, headless=config.HEADLESS) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            async def _on_response(response):
                if constants.LISTCOLLECTION_API not in response.url:
                    return
                try:
                    data = await response.json()
                except Exception as exc:
                    logger.warning("listcollection 响应解析失败：%s", exc)
                    return
                batch = parse_listcollection(data)
                batches.append(batch)
                logger.info(
                    "捕获 listcollection 批次 #%d：%d 条，cursor=%s has_more=%s",
                    len(batches), len(batch["items"]), batch["cursor"], batch["has_more"],
                )
                if on_batch and batch["items"]:
                    await on_batch({"page": len(batches), "items": batch["items"]})

            page.on("response", _on_response)
            await page.goto(constants.FAVORITES_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)

            cookies = await ctx.cookies()
            if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
                raise LoginExpiredError("抖音登录态缺失，请重新扫码登录")

            # 鼠标移到内容区中心，保证滚轮事件落在收藏列表上
            await page.mouse.move(640, 430)

            rounds, stall, last_merged = 0, 0, -1
            while rounds < constants.MAX_SCROLL_ROUNDS:
                merged = _merge_batches(batches)
                has_more = batches[-1]["has_more"] if batches else True
                if count and len(merged) >= count + skip:
                    logger.info("已收集 %d 条（目标 %d），停止滚动", len(merged), count + skip)
                    break
                if not has_more:
                    logger.info("接口提示 has_more=false（共 %d 条），停止滚动", len(merged))
                    break
                if stall >= constants.MAX_STALL_ROUNDS:
                    logger.warning(
                        "连续 %d 轮滚动无新增数据（当前 %d 条），提前结束避免空转",
                        stall, len(merged),
                    )
                    break

                scroll_info = await page.evaluate(_SCROLL_JS)
                await page.mouse.wheel(0, 2500)  # 补充真实滚轮事件，触发懒加载监听
                await page.wait_for_timeout(constants.SCROLL_INTERVAL_MS)
                rounds += 1

                new_merged = _merge_batches(batches)
                stall = stall + 1 if len(new_merged) == last_merged else 0
                last_merged = len(new_merged)
                logger.info(
                    "第 %d 轮滚动：%s scrollTop=%s/%s | 批次 %d，去重 %d 条",
                    rounds, scroll_info.get("mode"), scroll_info.get("scrollTop"),
                    scroll_info.get("scrollHeight"), len(batches), len(new_merged),
                )

            # 等最后一次滚动触发的响应落地
            await page.wait_for_timeout(1200)

        merged = _merge_batches(batches)
        window = merged[skip:] if not count else merged[skip: skip + count]
        last_has_more = bool(batches and batches[-1]["has_more"])
        logger.info(
            "[%s] 抓取完成：捕获批次 %d，去重 %d 条，返回 [%d:%d] 共 %d 条，has_more=%s",
            account.account_id, len(batches), len(merged), skip, skip + len(window),
            len(window), last_has_more,
        )
        return FetchResult(
            items=window,
            cursor=skip + len(window),
            # 返回满页且服务端提示还有更多 → 认为仍有余量；count=0 抓完全部，以接口 has_more 为准
            has_more=last_has_more and (not count or len(merged) >= skip + count),
            total=batches[0].get("total") if batches else 0,
        )
