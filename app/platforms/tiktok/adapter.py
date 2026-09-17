"""TikTok 适配器：声明式浏览器抓取 + API 直连。

浏览器模式（登录 / 滚动拦截）完全复用 DeclarativeAdapter（platforms/tiktok/
platform.json）；本类在其上叠加 API 直连能力：fetch_favorites 按
params.method 分发，并提供 get_profile / list_favorites / list_likes
三个 API 操作。

secUid 两个列表接口都要求入参且不落 cookie：登录成功后 refresh_profile
从浏览器会话提取（头像链接 → 个人主页 SSR 数据）回填账号 extra，运行期
extra 缺失时从 /favorites SSR 现提取兜底。
"""
import asyncio
import json
import logging
from pathlib import Path

from app import config
from app.platforms.base import (
    AccountContext,
    ApiOperation,
    ApiOperationParam,
    FetchResult,
)
from app.platforms.declarative import DeclarativeAdapter
from app.services import browser
from . import api_client
from . import constants

logger = logging.getLogger("favapi.tiktok")


class TikTokAdapter(DeclarativeAdapter):
    api_fetch_implemented = True  # 收藏列表支持 API 直连（params.method="api"）
    api_operations = (
        ApiOperation(
            op_id="get_profile",
            name="获取用户信息",
            description="API 直连获取用户信息（昵称/粉丝数/获赞数等，只读）；"
                        "默认当前登录账号，也可填任意用户 handle",
            params=(
                ApiOperationParam(
                    key="handle", label="用户 handle（可选）", type="text",
                    placeholder="例如：summerney",
                    help="留空 = 当前登录账号",
                ),
            ),
        ),
        ApiOperation(
            op_id="list_favorites",
            name="获取收藏列表",
            description="API 直连拉取当前账号收藏列表（只读，不入库，需活跃登录态）",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认 20",
                    help="返回条数上限",
                ),
                ApiOperationParam(
                    key="sec_uid", label="secUid（可选）", type="text",
                    help="默认自动提取；提取失败时手动填写（个人主页源码中可见）",
                ),
            ),
        ),
        ApiOperation(
            op_id="list_likes",
            name="获取点赞列表",
            description="API 直连拉取当前账号点赞列表（只读，不入库）；"
                        "私密点赞（默认设置）接口只返回空列表，非报错",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认 20",
                    help="返回条数上限",
                ),
                ApiOperationParam(
                    key="sec_uid", label="secUid（可选）", type="text",
                    help="默认自动提取；提取失败时手动填写（个人主页源码中可见）",
                ),
            ),
        ),
    )

    def __init__(self, base_dir: Path):
        spec = json.loads((Path(base_dir) / "platform.json").read_text(encoding="utf-8"))
        super().__init__(spec, base_dir=Path(base_dir))

    async def fetch_favorites(self, account: AccountContext, params: dict,
                              on_batch=None) -> FetchResult:
        if self.resolve_fetch_method(params) == "api":
            return await self.fetch_favorites_api(account, params, on_batch)
        return await super().fetch_favorites(account, params, on_batch)

    async def fetch_favorites_api(self, account: AccountContext, params: dict,
                                  on_batch=None) -> FetchResult:
        """API 直连：profile cookies + curl_cffi 直连 user/collect/item_list。

        cursor 语义与浏览器模式一致（已抓取条数偏移）；接口翻页内部用
        服务端毫秒时间戳游标。
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
        sec_uid = await self._resolve_sec_uid(account, params, cookie_header)
        collected, last_has_more = await self._fetch_collect_with_fallback(
            account, cookie_header, sec_uid,
            count=(count + skip) if count else 0, on_batch=on_batch)
        window = collected[skip:] if not count else collected[skip: skip + count]
        logger.info("[%s] API 直连抓取完成：共 %d 条，返回 [%d:%d] %d 条",
                    account.account_id, len(collected), skip, skip + len(window),
                    len(window))
        return FetchResult(
            items=window,
            cursor=skip + len(window),
            has_more=last_has_more and (not count or len(collected) >= skip + count),
            total=len(collected),
        )

    async def execute_api_operation(
        self, op_id: str, account: AccountContext, params: dict, on_event=None
    ) -> dict:
        if op_id == "get_profile":
            return await self._op_get_profile(account, params)
        if op_id == "list_favorites":
            cookie_header = await api_client.profile_cookie_header(account.profile_path)
            sec_uid = await self._resolve_sec_uid(account, params, cookie_header)
            count = _count_of(params)

            async def _fetch(c, cb):
                return await self._fetch_collect_with_fallback(
                    account, c, sec_uid, count, on_batch=cb)

            return await self._op_list(account, params, on_event, _fetch, "收藏")
        if op_id == "list_likes":
            cookie_header = await api_client.profile_cookie_header(account.profile_path)
            sec_uid = await self._resolve_sec_uid(account, params, cookie_header)
            return await self._op_list(
                account, params, on_event,
                lambda c, cb: api_client.fetch_favorite(c, sec_uid, _count_of(params), on_batch=cb),
                "点赞")
        raise ValueError(f"未知操作：{op_id}")

    async def _op_get_profile(self, account: AccountContext, params: dict) -> dict:
        """获取用户信息：handle 优先参数；空 = 本人（common-app-context，需登录）。"""
        handle = str((params or {}).get("handle") or "").strip().lstrip("@")
        if handle:
            info = await asyncio.to_thread(api_client.fetch_user_detail, handle, None)
            logger.info("[%s] API 操作 get_profile(@%s)：%s",
                        account.account_id, handle, info.get("nickname"))
            return info
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        me = await asyncio.to_thread(api_client.fetch_app_context, cookie_header)
        # 公开资料（粉丝数等 stats）从个人主页补全，无则用身份基础信息
        try:
            detail = await asyncio.to_thread(
                api_client.fetch_user_detail, me.get("unique_id"), None)
            detail["odin_id"] = me.get("odin_id")
            detail["user_id"] = detail.get("user_id") or me.get("user_id")
            info = detail
        except RuntimeError:
            info = {**me, "stats": {}}
        logger.info("[%s] API 操作 get_profile：%s(@%s)",
                    account.account_id, info.get("nickname"), info.get("unique_id"))
        return info

    async def _op_list(self, account: AccountContext, params: dict, on_event,
                       fetcher, label: str) -> dict:
        """只读列表操作共用实现（收藏 / 点赞）：count 限制 + 摘要输出。

        fetcher(cookie_header, on_batch) → (items, has_more)。
        """
        raw_count = str((params or {}).get("count") or "").strip()
        count = (min(max(int(raw_count), 0), constants.MAX_COUNT)
                 if raw_count.isdigit() else constants.DEFAULT_COUNT)
        logger.info("[%s] API 操作拉取%s列表：count=%s",
                    account.account_id, label, count or "全部")

        async def _collect_progress(batch: dict):
            if on_event:
                await on_event({
                    "type": "stage", "stage": "collecting",
                    "page": batch.get("page"), "total_fetched": len(batch.get("items") or []),
                })

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        collected, has_more = await fetcher(cookie_header, _collect_progress)
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

    async def _fetch_collect_with_fallback(self, account: AccountContext,
                                           cookie_header: str, sec_uid: str,
                                           count: int, on_batch=None):
        """收藏列表：API 直连优先，空响应（风控拦截）时降级浏览器页面拦截。

        collect 接口的签名（X-Gnarly）由站点 web worker 在请求构造时生成，
        不 hook 页面 fetch（JS Reverse 实测），直连无法复刻；浏览器模式下由
        站点自身发起请求，拦截响应即可。
        返回 (items, has_more)。
        """
        try:
            return await api_client.fetch_collect(cookie_header, sec_uid, count,
                                                  on_batch=on_batch)
        except RuntimeError as exc:
            logger.warning("[%s] 收藏直连被拦截（%s），降级浏览器拦截模式",
                           account.account_id, exc)
        owner = await self._owner_extra(account)
        handle = str(owner.get("unique_id") or "").strip()
        if not handle:
            me = await asyncio.to_thread(api_client.fetch_app_context, cookie_header)
            handle = me.get("unique_id")
        return await self._collect_via_browser(account, handle, count, on_batch)

    async def _collect_via_browser(self, account: AccountContext, handle: str,
                                   count: int, on_batch=None):
        """浏览器拦截本人主页 Saved 标签的 collect 响应并滚动翻页。"""
        from .parser import parse_item_list

        batches: list[dict] = []

        async def _on_response(response):
            if "/api/user/collect/item_list/" not in response.url:
                return
            try:
                data = await response.json()
            except Exception:
                return
            batch = parse_item_list(data)
            if batch["items"] or batches:
                batches.append(batch)
                logger.info("[%s] 捕获 collect 批次 #%d：%d 条，hasMore=%s",
                            account.account_id, len(batches), len(batch["items"]),
                            batch["has_more"])
                if on_batch and batch["items"]:
                    await on_batch({"page": len(batches), "items": batch["items"]})

        async with browser.session(account.profile_path, headless=config.HEADLESS,
                                   proxy=api_client.resolve_proxy()) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            page.on("response", _on_response)
            await page.goto(f"{constants.HOMEPAGE}/@{handle}",
                            wait_until="domcontentloaded")
            # 首批由主页预取或 Saved 标签触发；等 hydration 后尝试点击标签
            await page.wait_for_timeout(6000)
            if not batches:
                try:
                    await page.evaluate("""() => {
                        const cands = Array.from(
                            document.querySelectorAll('[data-e2e="saved-tab"], [role="tab"]'))
                            .filter(el => /saved|已保存|收藏|儲存/i.test(
                                el.innerText || '') ||
                                /saved/i.test(el.getAttribute('data-e2e') || ''));
                        if (cands.length) cands[0].click();
                    }""")
                    logger.info("[%s] 已尝试点击 Saved 标签", account.account_id)
                except Exception as exc:
                    logger.debug("[%s] 点击 Saved 标签失败：%s", account.account_id, exc)
            for _ in range(15):
                if batches:
                    break
                await page.wait_for_timeout(1000)

            # 滚动加载余页（douyin 浏览器模式同款节奏）
            rounds, stall = 0, 0
            while rounds < constants.MAX_SCROLL_ROUNDS:
                seen = sum(len(b["items"]) for b in batches)
                has_more = batches[-1]["has_more"] if batches else True
                if (count and seen >= count) or (batches and not has_more):
                    break
                if stall >= constants.MAX_STALL_ROUNDS:
                    logger.warning("[%s] 连续 %d 轮无新增，提前结束", account.account_id, stall)
                    break
                before = seen
                await page.mouse.wheel(0, 2500)
                await page.wait_for_timeout(1800)
                rounds += 1
                seen = sum(len(b["items"]) for b in batches)
                stall = stall + 1 if seen == before else 0
            await page.wait_for_timeout(1200)

        merged: dict[str, dict] = {}
        for batch in batches:
            for item in batch["items"]:
                merged.setdefault(item["content_id"], item)
        items = list(merged.values())
        has_more = bool(batches and batches[-1]["has_more"])
        logger.info("[%s] 浏览器拦截 collect 完成：批次 %d，去重 %d 条",
                    account.account_id, len(batches), len(items))
        return items, has_more

    async def _resolve_sec_uid(self, account: AccountContext, params: dict,
                               cookie_header: str) -> str:
        """secUid 三级解析：操作参数 → 账号 extra → common-app-context 现提取。"""
        sec_uid = str((params or {}).get("sec_uid") or "").strip()
        if sec_uid:
            return sec_uid
        owner = await self._owner_extra(account)
        sec_uid = str(owner.get("sec_uid") or "").strip()
        if sec_uid:
            return sec_uid
        sec_uid = await asyncio.to_thread(api_client.resolve_self_sec_uid, cookie_header) or ""
        if sec_uid:
            logger.info("[%s] 从 /favorites SSR 提取到 secUid", account.account_id)
            return sec_uid
        raise ValueError(
            "无法获取 secUid：请先完成登录（自动回填身份），或在参数中手动填写 sec_uid")

    @staticmethod
    async def _owner_extra(account: AccountContext) -> dict:
        """读取账号 extra 里回填的 TikTok 主人信息（无则空 dict）。"""
        from app.services import account_manager  # 延迟导入避免循环依赖

        row = await account_manager.get_account(account.account_id)
        if not row:
            return {}
        try:
            extra = json.loads(row.get("extra") or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return extra.get("tiktok") or {}

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：common-app-context 直读（纯 HTTP，无需浏览器导航）。

        secUid 不落 cookie 且个人主页 SSR 在登录态下不稳定（实测），
        webapp 身份的唯一可靠来源是 app-context（SSR 或本接口）。
        """
        import json as _json  # 局部导入，避免与函数内 account_manager 流程耦合

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        try:
            me = await asyncio.to_thread(api_client.fetch_app_context, cookie_header)
        except Exception as exc:
            logger.warning("[%s] TikTok 身份回填失败：%s", account.account_id, exc)
            return
        owner = {
            "user_id": me.get("user_id"),
            "unique_id": me.get("unique_id"),
            "sec_uid": me.get("sec_uid"),
            "nickname": me.get("nickname"),
            "avatar": me.get("avatar"),
        }
        from app.services import account_manager  # 延迟导入避免循环依赖

        row = await account_manager.get_account(account.account_id)
        if row is None:
            return
        try:
            extra = _json.loads(row.get("extra") or "{}")
        except (TypeError, _json.JSONDecodeError):
            extra = {}
        extra["tiktok"] = {"owner": owner}
        await account_manager.update_account(
            account.account_id, extra=_json.dumps(extra, ensure_ascii=False)
        )
        logger.info("[%s] 身份信息已回填：%s(@%s)",
                    account.account_id, owner.get("nickname"), owner.get("unique_id"))


def _count_of(params: dict) -> int:
    """操作参数 count → [0, MAX_COUNT]，非法/缺省取 DEFAULT_COUNT。"""
    raw = str((params or {}).get("count") or "").strip()
    return (min(max(int(raw), 0), constants.MAX_COUNT)
            if raw.isdigit() else constants.DEFAULT_COUNT)
