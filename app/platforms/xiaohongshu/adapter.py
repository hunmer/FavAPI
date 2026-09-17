"""小红书适配器：扫码登录 / 登录态检查 / 收藏列表抓取（响应拦截 + 滚动加载）。

edith.xiaohongshu.com 的 collect/page 接口有 x-s/x-t 签名校验，浏览器模式沿用
抖音方案：打开个人主页收藏 tab 滚动触发懒加载，拦截页面自身的 collect/page 响应
（签名由页面 JS 完成）。API 直连模式（method="api"）用 xhshow 纯算签名 +
curl_cffi 直连（见 api_client.py），无需页面参与。
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
from app.utils import filter_by_date_window, parse_date_window
from . import api_client, constants
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
    home_url = constants.HOME_URL
    implemented = True
    supported_actions = ("list_favorites",)
    api_fetch_implemented = True  # API 直连：xhshow 纯算签名 + curl_cffi（见 api_client.py）

    api_operations = (
        ApiOperation(
            op_id="list_favorites",
            name="获取收藏列表",
            description="API 直连拉取收藏笔记列表（只读，不入库），可按笔记发布日期过滤",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认 20",
                    help="返回条数上限；日期区间过滤在拉取后应用",
                ),
                ApiOperationParam(
                    key="date_from", label="发布日期从", type="date",
                    help="可选；接口无收藏时间，统一按笔记发布时间判定",
                ),
                ApiOperationParam(
                    key="date_to", label="发布日期至", type="date",
                    help="可选，闭区间（含当天）",
                ),
                ApiOperationParam(
                    key="user_id", label="用户 ID（可选）", type="text",
                    help="默认当前登录用户；查他人需对方收藏列表公开",
                ),
            ),
        ),
        ApiOperation(
            op_id="list_likes",
            name="获取点赞列表",
            description="API 直连拉取点赞（喜欢）笔记列表（只读，不入库），可按笔记发布日期过滤",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认 20",
                    help="返回条数上限；日期区间过滤在拉取后应用",
                ),
                ApiOperationParam(
                    key="date_from", label="发布日期从", type="date",
                    help="可选；接口无点赞时间，统一按笔记发布时间判定",
                ),
                ApiOperationParam(
                    key="date_to", label="发布日期至", type="date",
                    help="可选，闭区间（含当天）",
                ),
                ApiOperationParam(
                    key="user_id", label="用户 ID（可选）", type="text",
                    help="默认当前登录用户；查他人需对方点赞列表公开",
                ),
            ),
        ),
        ApiOperation(
            op_id="collect_note",
            name="收藏笔记",
            description="收藏指定笔记（API 直连执行，需活跃登录态）",
            params=(
                ApiOperationParam(
                    key="note_id", label="笔记 ID", type="text", required=True,
                    placeholder="例如：6aa3e227000000002503650b",
                    help="24 位十六进制笔记 id，可在笔记链接中获取",
                ),
            ),
        ),
        ApiOperation(
            op_id="uncollect_multi",
            name="批量取消收藏",
            description="按 ID 列表批量取消收藏笔记（操作不可恢复）",
            danger=True,
            params=(
                ApiOperationParam(
                    key="note_ids", label="笔记 ID 列表", type="textarea", required=True,
                    placeholder="ID 之间用逗号或换行分隔，例如：\n6aa3e227000000002503650b\n6aa797b3000000002b013ac9",
                    help="要取消收藏的笔记 id 列表",
                ),
            ),
        ),
        ApiOperation(
            op_id="like_note",
            name="点赞笔记",
            description="给指定笔记点赞（API 直连执行）",
            params=(
                ApiOperationParam(
                    key="note_oid", label="笔记 ID", type="text", required=True,
                    placeholder="例如：6aa3e227000000002503650b",
                    help="即笔记 id（接口字段名 note_oid）",
                ),
            ),
        ),
        ApiOperation(
            op_id="dislike_note",
            name="取消点赞",
            description="取消指定笔记的点赞（API 直连执行，可再次点赞恢复）",
            params=(
                ApiOperationParam(
                    key="note_oid", label="笔记 ID", type="text", required=True,
                    placeholder="例如：6aa3e227000000002503650b",
                    help="即笔记 id（接口字段名 note_oid）",
                ),
            ),
        ),
        ApiOperation(
            op_id="cancel_collect_by_date",
            name="按日期区间批量取消收藏",
            description="完整扫描收藏列表，按笔记发布日期区间匹配后批量取消收藏（操作不可恢复）",
            danger=True,
            params=(
                ApiOperationParam(
                    key="date_from", label="发布日期从", type="date", required=True,
                    help="必填（至少一个边界）；接口无收藏时间，按笔记发布时间（note_id 时间戳）判定",
                ),
                ApiOperationParam(
                    key="date_to", label="发布日期至", type="date",
                    help="可选，闭区间（含当天）；留空取该日期之后全部",
                ),
            ),
        ),
        ApiOperation(
            op_id="cancel_like_by_date",
            name="按日期区间批量取消喜欢",
            description="完整扫描点赞列表，按笔记发布日期区间匹配后逐条取消点赞（无批量接口，条数多时较慢；操作可逆但繁琐）",
            danger=True,
            params=(
                ApiOperationParam(
                    key="date_from", label="发布日期从", type="date", required=True,
                    help="必填（至少一个边界）；接口无点赞时间，按笔记发布时间（note_id 时间戳）判定",
                ),
                ApiOperationParam(
                    key="date_to", label="发布日期至", type="date",
                    help="可选，闭区间（含当天）；留空取该日期之后全部",
                ),
            ),
        ),
    )

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
        """解析当前登录用户 id（参考 B 站读 DedeUserID）。

        小红书 /user/profile 不带 id 是 404 页，必须先拿到自己的 id 才能进收藏 tab。
        优先签名调 /user/me 接口（快且权威，含 guest 判据）；失败回退导航头像链接 DOM。
        """
        try:
            await page.goto(constants.HOME_URL, wait_until="domcontentloaded")
        except Exception as exc:
            logger.warning("访问首页失败：%s", exc)
            return None

        try:
            uid = await self._me_user_id(ctx, page)
            if uid:
                logger.info("从 user/me 接口解析当前用户：%s", uid)
                return uid
        except Exception as exc:
            logger.warning("user/me 接口调用失败，回退 DOM 解析：%s", exc)

        # 回退：登录态水合后导航栏才由"登录"按钮变为用户头像组件（头像链接异步填充）
        try:
            await page.wait_for_selector(
                '.user.side-bar-component a[href*="/user/profile/"]', timeout=10_000
            )
            href = await page.evaluate(
                """() => {
                    const a = document.querySelector('.user.side-bar-component a[href*="/user/profile/"]');
                    return a ? a.getAttribute('href') : null;
                }"""
            )
        except Exception as exc:
            logger.warning("DOM 解析当前用户失败：%s", exc)
            return None
        uid = extract_user_id(href or "")
        if uid:
            logger.info("从首页导航头像链接解析当前用户：%s", uid)
        return uid

    @staticmethod
    async def _me(ctx, page) -> dict | None:
        """等待页面签名函数可用后，签名调用 /user/me 返回 data；游客/失败返回 None。"""
        sig = await page.evaluate(
            """async () => {
                for (let i = 0; i < 20; i++) {  // 最多等签名函数 10s
                    if (typeof window._webmsxyw === 'function') break;
                    await new Promise(r => setTimeout(r, 500));
                }
                if (typeof window._webmsxyw !== 'function') return null;
                return await window._webmsxyw('/api/sns/web/v2/user/me', '');
            }"""
        )
        if not isinstance(sig, dict) or not (sig.get("X-s") and sig.get("X-t")):
            return None
        resp = await ctx.request.get(
            constants.USER_ME_API,
            headers={
                "Origin": "https://www.xiaohongshu.com",
                "Referer": "https://www.xiaohongshu.com/",
                "x-s": sig["X-s"],
                "x-t": str(sig["X-t"]),
            },
        )
        if resp.status != 200:
            return None
        data = (await resp.json()).get("data") or {}
        if data.get("guest"):
            return None
        return data if is_user_id(str(data.get("user_id") or "")) else None

    @staticmethod
    async def _me_user_id(ctx, page) -> str | None:
        data = await XiaohongshuAdapter._me(ctx, page)
        return str(data.get("user_id")) if data else None

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

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：签名调 /user/me 取昵称/头像/红书号写入 extra。"""
        async with browser.session(account.profile_path, headless=True) as ctx:
            page, closing = await _open_page(ctx)
            try:
                await page.goto(constants.HOME_URL, wait_until="domcontentloaded")
                data = await self._me(ctx, page)
                if not data:
                    return
                owner = {
                    "user_id": str(data.get("user_id") or ""),
                    "red_id": str(data.get("red_id") or ""),
                    "nickname": data.get("nickname"),
                    "avatar": data.get("imageb") or data.get("images"),
                }
            finally:
                closing["closing"] = True  # 程序主动收尾，关窗不算异常

        from app.services import account_manager  # 延迟导入避免循环依赖

        saved = await account_manager.save_owner(account.account_id, "xiaohongshu", {"owner": owner})
        if saved is not None:
            logger.info("[%s] 身份信息已回填：%s(%s)", account.account_id, owner.get("nickname"), owner["user_id"])

    async def fetch_favorites(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        if self.resolve_fetch_method(params) == "api":
            return await self.fetch_favorites_api(account, params, on_batch)
        self.validate_params(params)
        user_id = self._target_user_id(params)
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

            if not user_id:  # 未指定目标 → 解析当前登录用户（小红书 profile 不带 id 是 404）
                user_id = await self._current_user_id(ctx, page)
                if not user_id:
                    closing["closing"] = True
                    raise LoginExpiredError(
                        "未指定目标用户，且无法获取当前登录用户 id（cookie/首页均未解析到）："
                        "请先扫码登录，或在参数中传入主页链接 / 用户 id"
                    )

            target_url = constants.PROFILE_URL.format(user_id=user_id)

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

    @staticmethod
    async def _api_user_id(account: AccountContext, cookies: dict, params: dict) -> str:
        """API 模式解析目标用户 id：params.url/user_id → 账号 extra 回填 → user/me 接口。

        小红书 profile 页不带 id 是 404，列表接口 user_id 必填；无浏览器上下文，
        用签名直连 user/me 兜底（同时校验登录态）。
        """
        uid = XiaohongshuAdapter._target_user_id(params or {})
        if uid:
            return uid
        from app.services import account_manager  # 延迟导入避免循环依赖

        row = await account_manager.get_account(account.account_id)
        owner = ((row or {}).get("extra") or {}).get("xiaohongshu", {}).get("owner") or {}
        uid = str(owner.get("user_id") or "")
        if is_user_id(uid):
            return uid
        me = await asyncio.to_thread(api_client.fetch_me, cookies)
        uid = str(me.get("user_id") or "")
        if is_user_id(uid):
            logger.info("[%s] user/me 解析当前用户：%s", account.account_id, uid)
            return uid
        raise ValueError(
            "无法确定目标用户 id：请在参数中传入主页链接 / user_id，"
            "或先完成一次登录刷新账号身份信息"
        )

    async def fetch_favorites_api(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        """API 直连：profile cookies + xhshow 签名 GET collect/page。

        cursor 语义与浏览器模式一致（已抓取条数偏移）；接口翻页内部用服务端游标。
        """
        self.validate_params(params)
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        logger.info(
            "[%s] API 直连抓取收藏：count=%s cursor=%d", account.account_id, count or "全部", skip
        )

        cookies = await api_client.profile_cookies(account.profile_path)
        user_id = await self._api_user_id(account, cookies, params)
        collected, last_has_more = await api_client.fetch_note_pages(
            cookies, constants.COLLECT_PAGE_URL, user_id,
            count=(count + skip) if count else 0, on_batch=on_batch,
        )
        window = collected[skip:] if not count else collected[skip: skip + count]
        logger.info(
            "[%s] API 直连抓取完成：共 %d 条，返回 [%d:%d] %d 条",
            account.account_id, len(collected), skip, skip + len(window), len(window),
        )
        return FetchResult(
            items=window,
            cursor=skip + len(window),
            has_more=last_has_more and (not count or len(collected) >= skip + count),
            total=len(collected),
        )

    async def execute_api_operation(
        self, op_id: str, account: AccountContext, params: dict, on_event=None
    ) -> dict:
        if op_id == "list_favorites":
            return await self._op_list_notes(account, params, on_event, constants.COLLECT_PAGE_URL, "收藏")
        if op_id == "list_likes":
            return await self._op_list_notes(account, params, on_event, constants.LIKE_PAGE_URL, "点赞")
        if op_id == "collect_note":
            return await self._op_collect_note(account, params)
        if op_id == "uncollect_multi":
            return await self._op_uncollect_multi(account, params, on_event)
        if op_id == "like_note":
            return await self._op_like_note(account, params, like=True)
        if op_id == "dislike_note":
            return await self._op_like_note(account, params, like=False)
        if op_id == "cancel_collect_by_date":
            return await self._op_cancel_by_date(account, params, on_event, batch=True)
        if op_id == "cancel_like_by_date":
            return await self._op_cancel_by_date(account, params, on_event, batch=False)
        raise ValueError(f"未知操作：{op_id}")

    @staticmethod
    def _note_id_param(params: dict, key: str) -> str:
        """校验并取出笔记 ID 参数（16~32 位十六进制）。"""
        note_id = str((params or {}).get(key) or "").strip()
        if not is_user_id(note_id):  # 与用户 id 同为 Mongo ObjectId 格式，形状校验复用
            raise ValueError(f"请填写有效的笔记 ID（16~32 位十六进制）：{note_id or '空'}")
        return note_id

    async def _op_collect_note(self, account: AccountContext, params: dict) -> dict:
        """收藏一条笔记。"""
        note_id = self._note_id_param(params, "note_id")
        logger.info("[%s] API 操作 collect_note：%s", account.account_id, note_id)
        cookies = await api_client.profile_cookies(account.profile_path)
        data = await asyncio.to_thread(api_client.collect_note, cookies, note_id)
        return {"note_id": note_id, "collected": True, "raw": data}

    async def _op_uncollect_multi(self, account: AccountContext, params: dict,
                                  on_event=None) -> dict:
        """批量取消收藏：按 UNCOLLECT_BATCH 分批，on_progress 逐批回调。"""
        raw = str((params or {}).get("note_ids") or "")
        note_ids = [t for t in (s.strip() for s in raw.replace("\n", ",").split(",")) if t]
        if not note_ids:
            raise ValueError("请填写要取消收藏的笔记 ID 列表")
        for note_id in note_ids:
            if not is_user_id(note_id):
                raise ValueError(f"笔记 ID 列表含无效项：{note_id}")

        async def _progress(batch_no: int, total_batches: int, done: int, ids: list[str]):
            if on_event:
                await on_event({
                    "type": "progress", "batch_no": batch_no,
                    "total_batches": total_batches, "done": done, "ids": ids,
                })

        logger.info("[%s] API 操作 uncollect_multi：%d 条", account.account_id, len(note_ids))
        cookies = await api_client.profile_cookies(account.profile_path)
        batches = [note_ids[i: i + constants.UNCOLLECT_BATCH]
                   for i in range(0, len(note_ids), constants.UNCOLLECT_BATCH)]
        uncollected = 0
        for i, chunk in enumerate(batches, start=1):
            await asyncio.to_thread(api_client.uncollect_notes, cookies, chunk)
            uncollected += len(chunk)
            logger.info("uncollect 第 %d/%d 批：%d 条", i, len(batches), len(chunk))
            await _progress(i, len(batches), uncollected, chunk)
            if i < len(batches):
                await asyncio.sleep(constants.UNCOLLECT_INTERVAL_SEC)
        return {"total": len(note_ids), "batches": len(batches), "uncollected": uncollected}

    async def _op_like_note(self, account: AccountContext, params: dict, like: bool) -> dict:
        """点赞 / 取消点赞一条笔记（同一接口族，body 字段均为 note_oid）。"""
        note_oid = self._note_id_param(params, "note_oid")
        op = "like_note" if like else "dislike_note"
        logger.info("[%s] API 操作 %s：%s", account.account_id, op, note_oid)
        cookies = await api_client.profile_cookies(account.profile_path)
        fn = api_client.like_note if like else api_client.dislike_note
        data = await asyncio.to_thread(fn, cookies, note_oid)
        return {"note_oid": note_oid, "liked": like, "raw": data}

    async def _op_cancel_by_date(self, account: AccountContext, params: dict,
                                 on_event, batch: bool) -> dict:
        """按发布日期区间批量取消收藏（batch=True）/ 点赞（batch=False）。

        列表按收藏/点赞时间倒序而条目时间为发布时间，两者不同序 → 无法提前
        终止，且取消会改变列表 → 必须完整扫描收集命中 ID 后再统一取消（同
        抖音 cancel_collect_by_window 策略）。取消点赞无批量接口，逐条执行。
        """
        label = "收藏" if batch else "点赞"
        dt_from, dt_to = parse_date_window(params or {})
        if not dt_from and not dt_to:
            raise ValueError("请至少填写一个日期边界（从/至），全留空会取消全部{label}记录".format(label=label))
        logger.info("[%s] API 操作按日期取消%s：区间=%s~%s", account.account_id, label, dt_from, dt_to)

        cookies = await api_client.profile_cookies(account.profile_path)
        user_id = await self._api_user_id(account, cookies, params)
        url = constants.COLLECT_PAGE_URL if batch else constants.LIKE_PAGE_URL

        # 阶段 1：完整扫描，按发布日期过滤收集命中 ID（content_id 去重）
        matched_ids: list[str] = []
        matched_seen: set[str] = set()
        scan_state = {"page": 0, "total_fetched": 0, "oldest": None}

        async def _scan_batch(batch: dict):
            scan_state["page"] = batch.get("page") or scan_state["page"]
            items = batch.get("items") or []
            scan_state["total_fetched"] += len(items)
            matched = filter_by_date_window(items, dt_from, dt_to)
            for it in matched:
                content_id = it.get("content_id")
                if content_id and content_id not in matched_seen:
                    matched_seen.add(content_id)
                    matched_ids.append(content_id)
            page_ts = [it.get("collected_at") for it in items if it.get("collected_at")]
            if page_ts:
                page_oldest = min(page_ts)
                if scan_state["oldest"] is None or page_oldest < scan_state["oldest"]:
                    scan_state["oldest"] = page_oldest
            if on_event:
                await on_event({
                    "type": "progress", "page": scan_state["page"],
                    "oldest_collected_at": scan_state["oldest"],
                    "fetched_this_page": len(items), "matched_this_page": len(matched),
                    "canceled": 0, "total_fetched": scan_state["total_fetched"],
                })

        await api_client.fetch_note_pages(cookies, url, user_id, count=0, on_batch=_scan_batch)
        logger.info("[%s] 扫描完成：%d 页 %d 条，命中 %d 条，开始取消",
                    account.account_id, scan_state["page"], scan_state["total_fetched"], len(matched_ids))

        # 阶段 2：统一取消（收藏走批量接口；点赞逐条）
        canceled = 0
        if batch:
            batches = [matched_ids[i: i + constants.UNCOLLECT_BATCH]
                       for i in range(0, len(matched_ids), constants.UNCOLLECT_BATCH)]
            for i, chunk in enumerate(batches, start=1):
                await asyncio.to_thread(api_client.uncollect_notes, cookies, chunk)
                canceled += len(chunk)
                if on_event:
                    await on_event({"type": "progress", "batch_no": i,
                                    "total_batches": len(batches), "done": canceled, "ids": chunk})
                if i < len(batches):
                    await asyncio.sleep(constants.UNCOLLECT_INTERVAL_SEC)
        else:
            for i, note_oid in enumerate(matched_ids, start=1):
                await asyncio.to_thread(api_client.dislike_note, cookies, note_oid)
                canceled += 1
                if on_event:
                    await on_event({"type": "progress", "batch_no": i,
                                    "total_batches": len(matched_ids), "done": canceled,
                                    "ids": [note_oid]})
                if i < len(matched_ids):
                    await asyncio.sleep(constants.UNCOLLECT_INTERVAL_SEC)

        return {
            "matched": len(matched_ids),
            "canceled": canceled,
            "pages": scan_state["page"],
            "stopped_early": False,
            "total_fetched": scan_state["total_fetched"],
        }

    async def _op_list_notes(self, account: AccountContext, params: dict,
                             on_event, url: str, label: str) -> dict:
        """只读拉取 note 列表（收藏/点赞共用），返回摘要，不入库；可按发布日期过滤。"""
        raw_count = str((params or {}).get("count") or "").strip()
        count = min(max(int(raw_count), 0), constants.MAX_COUNT) if raw_count.isdigit() else constants.DEFAULT_COUNT
        dt_from, dt_to = parse_date_window(params or {})
        logger.info("[%s] API 操作拉取%s列表：count=%s 区间=%s~%s",
                    account.account_id, label, count or "全部", dt_from, dt_to)

        async def _collect_progress(batch: dict):
            if on_event:
                await on_event({
                    "type": "stage", "stage": "collecting",
                    "page": batch.get("page"), "total_fetched": len(batch.get("items") or []),
                })

        cookies = await api_client.profile_cookies(account.profile_path)
        user_id = await self._api_user_id(account, cookies, params)
        collected, has_more = await api_client.fetch_note_pages(
            cookies, url, user_id, count, on_batch=_collect_progress
        )
        matched = filter_by_date_window(collected, dt_from, dt_to)
        summaries = [
            {
                "content_id": it.get("content_id"),
                "title": it.get("title"),
                "author_name": it.get("author_name"),
                "collected_at": it.get("collected_at"),
            }
            for it in matched[:100]
        ]
        return {
            "total": len(collected),
            "matched": len(matched),
            "has_more": has_more,
            "items": summaries,
            "note": "仅展示前 100 条摘要" if len(matched) > 100 else "",
        }
