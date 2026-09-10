"""小红书适配器：扫码登录 / 登录态检查 / 收藏列表抓取（响应拦截 + 滚动加载）。

edith.xiaohongshu.com 的 collect/page 接口有 x-s/x-t 签名校验，无法像 Bilibili
那样直接构造请求：沿用抖音方案，打开个人主页收藏 tab 滚动触发懒加载，拦截页面
自身的 collect/page 响应（签名由页面 JS 完成）。
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
from . import constants
from .parser import extract_user_id, is_user_id, parse_collect_page

logger = logging.getLogger("favapi.xiaohongshu")

# 登录态 DOM 判据：游客首页必有"登录"按钮、无导航用户区；扫码成功后前者消失、后者出现。
# （cookie 不可靠：游客打开首页也会被种 web_session）
_LOGIN_STATE_JS = """
() => ({
  loginBtn: !!document.querySelector('.login-btn'),
  navUser: !!document.querySelector('.user.side-bar-component'),
})"""

# 游客访问首页即会种下的 cookie；登录成功后新出现的键才是登录态特有（用于日志比对）
_VISITOR_COOKIE_KEYS = {
    "a1", "abRequestId", "acw_tc", "ets", "gid", "loadts", "sec_poison_id",
    "webBuild", "webId", "web_session", "websectiga", "xsecappid", "unread",
}

# 个人页收藏 tab 的滚动可能发生在内部容器而非 window：找到真正可滚动的容器设置 scrollTop
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


async def _open_page(ctx):
    """取现有页面或新建并加固：屏蔽页面脚本 window.close() 自主关窗（反爬）。

    返回 (page, closing)：closing["closing"] 置 True 后再退出 session，
    close 事件不再告警——仅"非程序主动关闭"才打警告，避免正常流程误报。
    """
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.add_init_script("window.close = () => {}")
    closing = {"closing": False}

    def _on_close():
        if not closing["closing"]:
            logger.warning("页面被意外关闭（非程序主动关闭）：疑似小红书反爬脚本或渲染进程崩溃")

    page.on("close", _on_close)
    return page, closing


class XiaohongshuAdapter(BasePlatformAdapter):
    platform = constants.PLATFORM
    display_name = constants.DISPLAY_NAME
    implemented = True
    supported_actions = ("list_favorites",)

    def validate_params(self, params: dict) -> None:
        raw_url = str(params.get("url") or "").strip()
        raw_uid = str(params.get("user_id") or "").strip()
        if not raw_url and not raw_uid:
            return  # 未指定 → 默认当前登录用户自己的收藏
        uid = extract_user_id(raw_url) or raw_uid
        if not is_user_id(uid):
            raise ValueError(
                "目标用户无效：url 需为 "
                "https://www.xiaohongshu.com/user/profile/{用户id}?tab=fav 形式的主页链接，"
                "或 user_id 传用户 id；留空则默认当前登录用户"
            )

    @staticmethod
    def _target_user_id(params: dict) -> str:
        return extract_user_id(str(params.get("url") or "")) or str(params.get("user_id") or "").strip()

    async def _current_user_id(self, ctx, page) -> str | None:
        """解析当前登录用户 id（参考 B 站读 DedeUserID）：先查 cookie，再从首页导航头像链接提取。

        小红书 /user/profile 不带 id 是 404 页，必须先拿到自己的 id 才能进收藏 tab。
        """
        for c in await ctx.cookies():
            if c.get("name") == "customerClientId" and is_user_id(c.get("value") or ""):
                logger.info("从 cookie customerClientId 解析当前用户：%s", c["value"])
                return c["value"]
        try:
            await page.goto(constants.HOME_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
            href = await page.evaluate(
                """() => {
                    const a = document.querySelector('.user.side-bar-component a[href*="/user/profile/"]');
                    return a ? a.getAttribute('href') : null;
                }"""
            )
        except Exception as exc:
            logger.warning("访问首页解析当前用户失败：%s", exc)
            return None
        uid = extract_user_id(href or "")
        if uid:
            logger.info("从首页导航头像链接解析当前用户：%s", uid)
        return uid

    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        """打开有头浏览器等待扫码；以 DOM 判据检测成功（游客也会被种 web_session，cookie 会误报）。"""
        timeout = timeout or config.LOGIN_TIMEOUT
        deadline = time.monotonic() + timeout
        logger.info("[%s] 打开登录窗口，等待扫码（最长 %ss）", account.account_id, timeout)
        async with browser.session(account.profile_path, headless=False) as ctx:
            page, closing = await _open_page(ctx)
            await page.goto(constants.HOME_URL, wait_until="domcontentloaded")
            checked = 0
            while time.monotonic() < deadline:
                checked += 1
                try:
                    state = await page.evaluate(_LOGIN_STATE_JS)
                except Exception:  # 页面导航/渲染中，稍后重试
                    state = {}
                if state and not state.get("loginBtn", True) and state.get("navUser"):
                    new_keys = sorted(
                        {c["name"] for c in await ctx.cookies()} - _VISITOR_COOKIE_KEYS
                    )
                    logger.info(
                        "[%s] 第 %d 次轮询检测到登录成功（登录按钮消失/用户区出现），"
                        "登录后新增 cookie：%s",
                        account.account_id, checked, new_keys or "无",
                    )
                    closing["closing"] = True
                    return True
                if checked % 10 == 0:
                    logger.info("[%s] 第 %d 次轮询未检测到登录（DOM 状态=%s）", account.account_id, checked, state)
                await asyncio.sleep(3)
            logger.warning("[%s] 等待扫码超时（%ss，共轮询 %d 次），登录未完成", account.account_id, timeout, checked)
            closing["closing"] = True
            return False

    async def check_login_status(self, account: AccountContext) -> bool:
        """登录态检查：仅读取 profile cookie，不导航页面 → 固定无头。"""
        async with browser.session(account.profile_path, headless=True) as ctx:
            cookies = await ctx.cookies()
            ok = browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS)
            logger.info("[%s] 登录态检查：%s", account.account_id, "有效" if ok else "无效")
            return ok

    async def fetch_favorites(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        self.validate_params(params)
        user_id = self._target_user_id(params)
        target_url = (
            constants.PROFILE_URL.format(user_id=user_id) if user_id else constants.FAVORITES_URL
        )
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        logger.info(
            "[%s] 开始抓取收藏：user=%s count=%s cursor=%d",
            account.account_id, user_id or "当前登录用户", count or "全部", skip,
        )

        batches: list[dict] = []
        async with browser.session(account.profile_path, headless=config.HEADLESS) as ctx:
            page, closing = await _open_page(ctx)

            async def _on_response(response):
                if constants.COLLECT_PAGE_API not in response.url:
                    return
                try:
                    data = await response.json()
                except Exception as exc:
                    logger.warning("collect/page 响应解析失败：%s", exc)
                    return
                batch = parse_collect_page(data)
                batches.append(batch)
                logger.info(
                    "捕获 collect/page 批次 #%d：%d 条，cursor=%s has_more=%s",
                    len(batches), len(batch["items"]), batch["cursor"], batch["has_more"],
                )
                if on_batch and batch["items"]:
                    await on_batch({"page": len(batches), "items": batch["items"]})

            page.on("response", _on_response)
            await page.goto(target_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)

            # 未登录访问收藏 tab 会弹登录框（游客也有 web_session，cookie 判据不可靠）
            login_popup = await page.evaluate(
                "() => !!document.querySelector('.login-container, .login-mask')"
            )
            if login_popup:
                closing["closing"] = True
                raise LoginExpiredError("小红书未登录（收藏页弹出登录框），请先扫码登录")

            # 鼠标移到内容区中心，保证滚轮事件落在收藏网格上
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
            closing["closing"] = True  # 程序主动收尾，关窗不算异常

        merged = _merge_batches(batches)
        if not merged:
            raise LoginExpiredError(
                "未捕获到任何收藏数据：账号可能未登录（游客也有 web_session，"
                "请重新扫码登录）或被风控拦截"
            )
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
            has_more=last_has_more and (not count or len(merged) > skip + len(window)),
            total=len(merged),
        )
