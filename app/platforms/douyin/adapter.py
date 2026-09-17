"""抖音适配器：扫码登录 / 登录态检查 / 收藏列表抓取（响应拦截 + 滚动加载）。"""
import asyncio
import logging
import re
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
from . import api_client
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
    api_fetch_implemented = True  # 收藏列表支持 API 直连（params.method="api"）
    api_operations = (
        ApiOperation(
            op_id="list_favorites",
            name="获取收藏视频列表",
            description="API 直连拉取当前账号收藏列表（只读，不入库），可选按收藏日期过滤",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认 20",
                    help="返回条数上限；日期区间过滤在抓取后应用",
                ),
                ApiOperationParam(
                    key="date_from", label="收藏日期从", type="date",
                    help="可选；无收藏时间时按发布时间判定",
                ),
                ApiOperationParam(
                    key="date_to", label="收藏日期至", type="date",
                    help="可选，闭区间（含当天）",
                ),
            ),
        ),
        ApiOperation(
            op_id="cancel_collect_multi",
            name="批量取消收藏",
            description="完整扫描所有收藏，按视频上传时间批量取消收藏（操作不可恢复）",
            danger=True,
            params=(
                ApiOperationParam(
                    key="aweme_ids", label="视频 ID 列表", type="textarea",
                    placeholder="ID 之间用逗号或换行分隔，例如：\n7684881459982748963\n7684870473406074122",
                    help="与日期区间二选一；填写日期区间时忽略本项",
                ),
                ApiOperationParam(
                    key="date_from", label="按日期区间：从", type="date",
                    help="填日期区间时会完整扫描收藏列表，无需手填 ID",
                ),
                ApiOperationParam(
                    key="date_to", label="按日期区间：至", type="date",
                    help="闭区间（含当天）",
                ),
                ApiOperationParam(
                    key="time_mode", label="日期判定方式", type="select",
                    options=(
                        ("collected", "按视频上传时间（推荐）"),
                        ("published", "按视频上传时间（兼容旧参数）"),
                    ),
                    help="抖音不提供真实加入收藏时间，当前统一使用视频自身 create_time",
                ),
            ),
        ),
        ApiOperation(
            op_id="list_likes",
            name="获取喜欢(点赞)列表",
            description="API 直连拉取当前账号喜欢列表（只读，不入库），可选按日期过滤",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认 20",
                    help="返回条数上限；日期区间过滤在抓取后应用",
                ),
                ApiOperationParam(
                    key="date_from", label="发布日期从", type="date",
                    help="可选；无点赞时间时按视频发布时间判定",
                ),
                ApiOperationParam(
                    key="date_to", label="发布日期至", type="date",
                    help="可选，闭区间（含当天）",
                ),
                ApiOperationParam(
                    key="sec_user_id", label="sec_user_id（可选）", type="text",
                    help="默认从登录态自动提取；提取失败时手动填写（喜欢页 URL 中可见）",
                ),
            ),
        ),
        ApiOperation(
            op_id="list_history",
            name="获取观看历史",
            description="API 直连拉取观看历史（只读，不入库）；需活跃登录态，失效时请先重新扫码",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认 20",
                    help="返回条数上限",
                ),
            ),
        ),
        ApiOperation(
            op_id="list_watchlater",
            name="获取稍后再看列表",
            description="API 直连拉取稍后再看列表（只读，不入库）",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认 20",
                    help="返回条数上限",
                ),
            ),
        ),
        ApiOperation(
            op_id="digg_item",
            name="点赞视频",
            description="给指定视频点赞（浏览器页面通道执行，需活跃登录态）",
            params=(
                ApiOperationParam(
                    key="aweme_id", label="视频 ID", type="text", required=True,
                    placeholder="例如：7685995248116503153",
                    help="纯数字 aweme_id，可在视频分享链接中获取",
                ),
            ),
        ),
        ApiOperation(
            op_id="cancel_digg_multi",
            name="批量取消点赞",
            description="按 ID 列表批量取消点赞（操作不可恢复，浏览器页面通道执行）",
            danger=True,
            params=(
                ApiOperationParam(
                    key="aweme_ids", label="视频 ID 列表", type="textarea", required=True,
                    placeholder="ID 之间用逗号或换行分隔，例如：\n7686197461799665984\n7686125901436145833",
                    help="要取消点赞的视频 aweme_id 列表",
                ),
            ),
        ),
    )

    async def execute_api_operation(
        self, op_id: str, account: AccountContext, params: dict, on_event=None
    ) -> dict:
        if op_id == "list_favorites":
            return await self._op_list_favorites(account, params, on_event)
        if op_id == "cancel_collect_multi":
            return await self._op_cancel_collect(account, params, on_event)
        if op_id == "list_likes":
            return await self._op_list_likes(account, params, on_event)
        if op_id == "list_history":
            return await self._op_list_summary(
                account, params, on_event, api_client.fetch_history, "观看历史")
        if op_id == "list_watchlater":
            return await self._op_list_summary(
                account, params, on_event, api_client.fetch_watchlater, "稍后再看")
        if op_id == "digg_item":
            return await self._op_digg_item(account, params)
        if op_id == "cancel_digg_multi":
            return await self._op_cancel_digg(account, params, on_event)
        raise ValueError(f"未知操作：{op_id}")

    async def _op_list_summary(self, account: AccountContext, params: dict, on_event,
                               fetcher, label: str) -> dict:
        """只读列表操作共用实现（观看历史 / 稍后再看）：count 限制 + 摘要输出。"""
        raw_count = str((params or {}).get("count") or "").strip()
        count = min(max(int(raw_count), 0), constants.MAX_COUNT) if raw_count.isdigit() else constants.DEFAULT_COUNT
        logger.info("[%s] API 操作拉取%s：count=%s", account.account_id, label, count or "全部")

        async def _collect_progress(batch: dict):
            if on_event:
                await on_event({
                    "type": "stage", "stage": "collecting",
                    "page": batch.get("page"), "total_fetched": len(batch.get("items") or []),
                })

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        collected, has_more = await fetcher(cookie_header, count, on_batch=_collect_progress)
        summaries = [
            {
                "content_id": it.get("content_id"),
                "title": it.get("title"),
                "author_name": it.get("author_name"),
                "collected_at": it.get("collected_at"),
            }
            for it in collected[:100]
        ]
        return {
            "total": len(collected),
            "has_more": has_more,
            "items": summaries,
            "note": "仅展示前 100 条摘要" if len(collected) > 100 else "",
        }

    async def _op_list_likes(self, account: AccountContext, params: dict, on_event=None) -> dict:
        """只读拉取喜欢(点赞)列表（可选日期过滤），返回摘要，不入库。"""
        raw_count = str((params or {}).get("count") or "").strip()
        count = min(max(int(raw_count), 0), constants.MAX_COUNT) if raw_count.isdigit() else constants.DEFAULT_COUNT
        dt_from, dt_to = parse_date_window(params or {})
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        sec_uid = str((params or {}).get("sec_user_id") or "").strip() or api_client.self_sec_uid(cookie_header)
        if not sec_uid:
            raise ValueError("无法从登录态提取 sec_user_id，请在参数中手动填写（喜欢页 URL 中可见）")
        logger.info("[%s] API 操作 list_likes：count=%s 区间=%s~%s",
                    account.account_id, count or "全部", dt_from, dt_to)

        async def _collect_progress(batch: dict):
            if on_event:
                await on_event({
                    "type": "stage", "stage": "collecting",
                    "page": batch.get("page"), "total_fetched": len(batch.get("items") or []),
                })

        collected, has_more = await api_client.fetch_like(
            cookie_header, sec_uid, count, on_batch=_collect_progress
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

    async def _op_digg_item(self, account: AccountContext, params: dict) -> dict:
        """给指定视频点赞（浏览器页面 fetch 通道，写接口有 JS 签名强校验）。"""
        aweme_id = str((params or {}).get("aweme_id") or "").strip()
        if not aweme_id.isdigit():
            raise ValueError("请填写要点赞的视频 ID（纯数字 aweme_id）")
        logger.info("[%s] API 操作 digg_item：%s", account.account_id, aweme_id)
        data = await api_client.digg_item_via_browser(account.profile_path, aweme_id)
        logger.info("[%s] 点赞完成：is_digg=%s", account.account_id, data.get("is_digg"))
        return {"aweme_id": aweme_id, "is_digg": data.get("is_digg")}

    async def _op_cancel_digg(self, account: AccountContext, params: dict, on_event=None) -> dict:
        """按 ID 列表批量取消点赞（浏览器页面 fetch 通道）。"""
        raw = str((params or {}).get("aweme_ids") or "")
        aweme_ids = [t.strip() for t in re.split(r"[\s,，;；]+", raw) if t.strip()]
        if not aweme_ids:
            raise ValueError("请填写要取消点赞的视频 ID 列表")
        if any(not t.isdigit() for t in aweme_ids):
            raise ValueError("aweme_ids 含非数字 ID，请检查输入")

        async def _batch_progress(info: dict):
            if on_event:
                await on_event({"type": "progress", **info})

        logger.info("[%s] 批量取消点赞：%d 条", account.account_id, len(aweme_ids))
        result = await api_client.cancel_digg_multi_via_browser(
            account.profile_path, aweme_ids, on_progress=_batch_progress)
        result["matched"] = len(aweme_ids)
        logger.info("[%s] 批量取消点赞完成：%s", account.account_id, result)
        return result

    async def _op_list_favorites(self, account: AccountContext, params: dict, on_event=None) -> dict:
        """只读拉取收藏列表（可选日期过滤），返回摘要，不入库。"""
        raw_count = str((params or {}).get("count") or "").strip()
        count = min(max(int(raw_count), 0), constants.MAX_COUNT) if raw_count.isdigit() else constants.DEFAULT_COUNT
        dt_from, dt_to = parse_date_window(params or {})
        logger.info("[%s] API 操作 list_favorites：count=%s 区间=%s~%s",
                    account.account_id, count or "全部", dt_from, dt_to)

        async def _collect_progress(batch: dict):
            if on_event:
                await on_event({
                    "type": "stage", "stage": "collecting",
                    "page": batch.get("page"), "total_fetched": len(batch.get("items") or []),
                })

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        collected, has_more = await api_client.fetch_listcollection(
            cookie_header, cursor=0, count=count, stop_before=dt_from, on_batch=_collect_progress
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

    async def _op_cancel_collect(self, account: AccountContext, params: dict, on_event=None) -> dict:
        """批量取消收藏：视频 ID 列表 / 收藏日期区间二选一（日期优先）。

        日期区间模式为管道式：逐页拉取，当页命中的立即取消并上报进度
        （含当前翻到的最早收藏时间与累计取消条数），翻过下界即提前终止。
        """
        raw = str((params or {}).get("aweme_ids") or "")
        aweme_ids = [t.strip() for t in re.split(r"[\s,，;；]+", raw) if t.strip()]
        dt_from, dt_to = parse_date_window(params or {})
        if not aweme_ids and not (dt_from or dt_to):
            raise ValueError("请填写视频 ID 列表或收藏日期区间（二选一）")
        if any(not t.isdigit() for t in aweme_ids):
            raise ValueError("aweme_ids 含非数字 ID，请检查输入")

        async def _progress(info: dict):
            if on_event:
                await on_event(info)

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        if dt_from or dt_to:
            time_mode = str((params or {}).get("time_mode") or "collected").lower()
            if time_mode not in ("collected", "published"):
                raise ValueError("time_mode 仅支持 collected / published")
            logger.info("[%s] 按日期区间取消收藏（%s，边拉边取消）：%s ~ %s",
                        account.account_id, time_mode, dt_from, dt_to)
            result = await api_client.cancel_collect_by_window(
                cookie_header, dt_from, dt_to, on_progress=_progress, time_mode=time_mode
            )
            if result["canceled"] == 0:
                result["note"] = "该日期区间内没有匹配的收藏，未执行取消"
            logger.info("[%s] 批量取消收藏完成：%s", account.account_id, result)
            return result

        logger.info("[%s] 批量取消收藏（按 ID 列表）：%d 条", account.account_id, len(aweme_ids))

        async def _batch_progress(info: dict):
            if on_event:
                await on_event({"type": "progress", **info})

        result = await api_client.cancel_collect_multi(cookie_header, aweme_ids, on_progress=_batch_progress)
        result["matched"] = len(aweme_ids)
        logger.info("[%s] 批量取消收藏完成：%s", account.account_id, result)
        return result

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
            "avatar": _avatar(user),  # 带签名 CDN 原链，save_owner 落盘防过期
        }
        from app.services import account_manager  # 延迟导入避免循环依赖

        saved = await account_manager.save_owner(account.account_id, "douyin", {"owner": owner})
        if saved is not None:
            logger.info("[%s] 身份信息已回填：%s(%s)", account.account_id, owner.get("nickname"), owner["uid"])

    async def fetch_favorites(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        if self.resolve_fetch_method(params) == "api":
            return await self.fetch_favorites_api(account, params, on_batch)
        return await self._fetch_favorites_browser(account, params, on_batch)

    async def fetch_favorites_api(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        """API 直连：profile cookies + curl-impersonate Chrome 指纹 POST listcollection。

        cursor 语义与浏览器模式一致（已抓取条数偏移）；接口翻页内部用服务端游标。
        """
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        logger.info(
            "[%s] API 直连抓取收藏：count=%s cursor=%d", account.account_id, count or "全部", skip
        )

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        collected, last_has_more = await api_client.fetch_listcollection(
            cookie_header, cursor=0, count=(count + skip) if count else 0, on_batch=on_batch
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

    async def _fetch_favorites_browser(
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
