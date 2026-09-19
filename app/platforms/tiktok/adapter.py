"""TikTok 适配器：声明式浏览器抓取 + API 直连。

浏览器模式（登录 / 滚动拦截）完全复用 DeclarativeAdapter（platforms/tiktok/
platform.json）；本类在其上叠加 API 直连能力：收藏 / 喜欢两个抓取目标
（fetch_by_action 分发）+ get_profile / list_favorites / list_likes /
resolve_download_urls 四个 API 操作 + 特别关注（follows）体系。

secUid 两个列表接口都要求入参且不落 cookie：登录成功后 refresh_profile
从浏览器会话提取（头像链接 → 个人主页 SSR 数据）回填账号 extra，运行期
extra 缺失时从 /favorites SSR 现提取兜底。

follows 体系走页面通道（签名强校验，见 api_client 末尾逆向结论）：
cookie 仅为登录态凭证（TTL 缓存），实际请求在共享页面会话内完成，
profile 路径经 cookie → profile 映射传递（follows API 层只下发 cookie）。
"""
import asyncio
import json
import logging
import re
import time
from pathlib import Path

from app import config
from app.platforms.base import (
    AccountContext,
    ApiOperation,
    ApiOperationParam,
    FetchResult,
    FetchTarget,
    PARAM_COUNT,
    PARAM_CURSOR,
    PARAM_DATE_FROM,
    PARAM_DATE_TO,
)
from app.platforms.declarative import DeclarativeAdapter
from app.services import browser
from app.utils import now_iso
from . import api_client
from . import constants

logger = logging.getLogger("favapi.tiktok")

# 帖子链接中的 item_id（/video/{id} 与 /photo/{id} 两种路径）
_ITEM_URL_PATTERN = re.compile(r"(?:video|photo)/(\d{6,})")
# TikTok 博主主键 secUid 的格式（MS4wLjAB 固定前缀 + base62 变体）
_SEC_UID_FULL = re.compile(r"MS4wLjAB[A-Za-z0-9_.-]+")


class TikTokAdapter(DeclarativeAdapter):
    api_fetch_implemented = True  # 收藏列表支持 API 直连（params.method="api"）
    download_api_implemented = True  # 支持按帖子 ID/链接解析下载直链（平台下载 → aria2c）
    follows_api_implemented = True  # 特别关注体系：关注列表 / 博主主页作品 / 播放 / 一键同步
    # 可抓取入库的列表目标（source 为 favorites 来源标记；空 = 收藏列表）
    fetch_targets = (
        FetchTarget(
            action="list_favorites", name="抓取收藏列表",
            description="API 直连抓取当前账号收藏列表并入库（需活跃登录态）",
            params=[PARAM_COUNT, PARAM_CURSOR, PARAM_DATE_FROM, PARAM_DATE_TO],
        ),
        FetchTarget(
            action="list_likes", name="抓取喜欢列表", source="喜欢列表",
            description="API 直连抓取当前账号喜欢（点赞）帖子并入库；"
                        "私密点赞（TikTok 默认设置）接口只返回空列表，需先在平台设为公开点赞",
            params=[
                PARAM_COUNT, PARAM_CURSOR,
                ApiOperationParam(
                    key="sec_uid", label="secUid（可选）", type="text",
                    help="默认自动提取；提取失败时手动填写（个人主页源码中可见）",
                ),
            ],
        ),
    )
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
                    placeholder="默认全部",
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
                    placeholder="默认全部",
                    help="返回条数上限",
                ),
                ApiOperationParam(
                    key="sec_uid", label="secUid（可选）", type="text",
                    help="默认自动提取；提取失败时手动填写（个人主页源码中可见）",
                ),
            ),
        ),
        ApiOperation(
            op_id="resolve_download_urls",
            name="解析下载直链",
            description="按帖子 ID/链接返回可下载直链（视频多档画质/图文逐张原图，只读，"
                        "供平台下载/aria2c 使用）；详情走帖子页 SSR 公开数据，无需登录态",
            params=(
                ApiOperationParam(
                    key="item_id", label="帖子链接或 ID", type="text", required=True,
                    placeholder="例如：7680180904886635794（可粘贴完整链接）",
                    help="视频（/video/）与图文（/photo/）链接均支持，自动提取数字 ID",
                ),
            ),
        ),
    )

    def __init__(self, base_dir: Path):
        spec = json.loads((Path(base_dir) / "platform.json").read_text(encoding="utf-8"))
        super().__init__(spec, base_dir=Path(base_dir))
        # follows 登录态缓存：cookie TTL 缓存 + cookie → (profile, secUid) 映射
        # （follows API 层只下发 cookie 头，页面通道所需的 profile 与身份从这里找回）
        self._follows_cookie_cache: dict[str, dict] = {}
        self._follows_by_cookie: dict[str, tuple[str, str]] = {}

    # ---------- 特别关注（follows）体系 ----------

    async def follows_profile_cookie(self, account: AccountContext) -> str:
        """取登录 cookie（TTL 缓存 120s；TikTok follows 请求实际走页面通道，
        cookie 仅作登录态凭证与 profile/身份的关联键）。"""
        cached = self._follows_cookie_cache.get(account.account_id)
        if cached and time.monotonic() - cached["ts"] < 120:
            return cached["cookie"]
        cookie = await api_client.profile_cookie_header(account.profile_path)
        sec_uid = str((await self._owner_extra(account)).get("sec_uid") or "")
        if not sec_uid:
            try:  # extra 缺失时现提取（顺带完成真实登录校验）
                me = await asyncio.to_thread(api_client.fetch_app_context, cookie)
                sec_uid = me.get("sec_uid") or ""
            except Exception as exc:
                logger.warning("follows secUid 提取失败：%s", exc)
        self._follows_by_cookie[cookie] = (account.profile_path, sec_uid)
        self._follows_cookie_cache[account.account_id] = {"cookie": cookie, "ts": time.monotonic()}
        return cookie

    def follows_self_uid(self, cookie_header: str) -> str:
        return self._follows_by_cookie.get(cookie_header, ("", ""))[1]

    def follows_validate_uid(self, sec_uid: str) -> None:
        if not _SEC_UID_FULL.fullmatch(sec_uid or ""):
            raise ValueError(
                "TikTok 博主主键需为 secUid（MS4wLjAB 开头的字符串），"
                "见个人主页源码中的 secUid 字段")

    def _follows_profile_of(self, cookie_header: str) -> str:
        profile = self._follows_by_cookie.get(cookie_header, ("", ""))[0]
        if not profile:
            raise RuntimeError("页面通道缺少账号上下文（profile），请重新发起请求")
        return profile

    async def follows_fetch_following(self, cookie_header: str, self_uid: str,
                                      count: int = 0, on_batch=None) -> tuple[list[dict], bool]:
        # 条目结构已由 parse_following_list 对齐 follows 契约统一结构
        return await api_client.fetch_following_via_page(
            self._follows_profile_of(cookie_header), self_uid, count, on_batch=on_batch)

    async def follows_fetch_posts_page(self, cookie_header: str, sec_uid: str,
                                       cursor: int | str = 0, count: int = 18) -> dict:
        # TikTok cursor 为服务端毫秒时间戳游标（首页 0），末页归 0 对齐统一语义
        batch = await api_client.fetch_post_page_via_page(
            self._follows_profile_of(cookie_header), sec_uid,
            max(0, int(cursor or 0)), min(count, 35))
        batch["cursor"] = batch["cursor"] if batch["has_more"] else 0
        return batch

    async def follows_play_info(self, cookie_header: str, content_id: str) -> dict:
        m = _ITEM_URL_PATTERN.search(str(content_id or ""))
        item_id = m.group(1) if m else str(content_id or "").strip()
        if not item_id.isdigit():
            raise ValueError("TikTok 作品 ID 需为纯数字帖子 ID（或含 /video/、/photo/ 的链接）")
        # 匿名 SSR 通道解析（无需登录态）；视频直链绑定该会话（跨会话 cookie 403），
        # 会话 cookie 随各直链登记到媒体代理，/follows/media 按 URL 精确注入
        from app.services import follow_store

        info, session_cookie = await asyncio.to_thread(
            api_client.fetch_post_play_info, item_id)
        media_urls = list(info.get("video_urls") or [])
        media_urls += [img.get("url") for img in info.get("images") or []]
        if info.get("music_url"):
            media_urls.append(info["music_url"])
        for url in media_urls:
            follow_store.register_media_cookie(url, session_cookie)
        return info

    async def sync_author_posts(self, account: AccountContext, author_row: dict,
                                cookie_header: str, count: int) -> list[dict]:
        """拉取单博主最新 count 条作品（通用 content 行），并回填 last_synced_at / 身份字段。

        不负责入库：follows /sync 路由与 follow_sync 抓取目标（task 体系统一入库）共用本方法。
        author_id 改写为博主 secUid（contents 表未读数按 author_id = follow_authors.sec_uid 关联）。
        """
        from app.database import db  # 延迟导入：平台层仅此方法触库
        from app.services import follow_store

        items, _ = await api_client.fetch_post_via_page(
            account.profile_path, author_row["sec_uid"], count)
        items = items[:count]
        sec_uid = author_row["sec_uid"]
        for it in items:
            it["author_id"] = sec_uid
        author_name = next((it.get("author_name") for it in items if it.get("author_name")), None)
        await db.execute(
            """UPDATE follow_authors SET last_synced_at = ?,
                   uid = COALESCE(NULLIF(?, ''), uid),
                   nickname = COALESCE(NULLIF(?, ''), nickname)
               WHERE sec_uid = ?""",
            (now_iso(), "", author_name or "", sec_uid),
        )
        # 列表接口不带作者头像：本地文件缺失时按库中 URL（关注列表入库）补下自愈
        if follow_store.avatar_local_path(sec_uid) is None:
            source_url = (author_row.get("avatar_url") or "").strip()
            if source_url:
                await asyncio.to_thread(follow_store.download_avatar, sec_uid, source_url)
        return items

    async def fetch_favorites(self, account: AccountContext, params: dict,
                              on_batch=None) -> FetchResult:
        # 浏览器模拟模式已移除，仅保留 API 直连（collect 直连被风控拦截时
        # 由 _fetch_collect_with_fallback 内部降级页面拦截）；method 入口保留
        self.resolve_fetch_method(params)
        return await self.fetch_favorites_api(account, params, on_batch)

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

    async def fetch_by_action(
        self, action: str, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        if action == "list_likes":
            return await self._fetch_likes(account, params, on_batch)
        return await self.fetch_favorites(account, params, on_batch)

    async def _fetch_likes(self, account: AccountContext, params: dict,
                           on_batch=None) -> FetchResult:
        """喜欢(点赞)列表抓取入库（API 直连 favorite/item_list，source=喜欢列表）。

        cursor 语义与收藏一致（已抓取条数偏移）；接口翻页用服务端毫秒时间戳游标。
        私密点赞（默认设置）接口返回空列表非报错，target 描述已提示。
        """
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        logger.info("[%s] API 直连抓取喜欢列表：count=%s cursor=%d",
                    account.account_id, count or "全部", skip)

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        sec_uid = await self._resolve_sec_uid(account, params, cookie_header)
        collected, last_has_more = await api_client.fetch_favorite(
            cookie_header, sec_uid,
            count=(count + skip) if count else 0, on_batch=on_batch)
        window = collected[skip:] if not count else collected[skip: skip + count]
        logger.info("[%s] 喜欢列表抓取完成：共 %d 条，返回 [%d:%d] %d 条",
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
        if op_id == "resolve_download_urls":
            source = str((params or {}).get("item_id") or "").strip()
            if not source:
                raise ValueError("请填写 TikTok 帖子链接或数字 ID")
            return await self.resolve_download_urls(account, source)
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

    async def resolve_download_urls(self, account: AccountContext, content_id: str) -> list[dict]:
        """按帖子 ID（或完整链接）解析可下载直链（首项为推荐画质/首张图）。

        详情走帖子页 SSR 公开数据（无需登录态，见 api_client.fetch_post_detail）；
        视频直链下载需页面会话 cookie（tt_chain_token），随链接 headers 注入
        aria2c；图文直链仅 UA 即可。作者信息随链接下发（下载分类模板变量来源）。
        """
        source = str(content_id or "").strip()
        m = _ITEM_URL_PATTERN.search(source)
        item_id = m.group(1) if m else source
        if not item_id.isdigit():
            raise ValueError("tiktok 下载解析需要纯数字帖子 ID，或含 /video/、/photo/ 的链接")
        logger.info("[%s] 解析下载直链：item_id=%s", account.account_id, item_id)
        result = await asyncio.to_thread(api_client.fetch_post_detail, item_id)
        headers = {
            "user-agent": constants.USER_AGENT,
            "referer": constants.POST_DETAIL_URL.format(item_id=item_id),
            "cookie": result.get("cookie_header") or "",
        }
        for link in result["links"]:
            if link.get("url"):
                link["headers"] = headers
            link.setdefault("author_name", result.get("author_name"))
            link.setdefault("author_id", result.get("author_id"))
        return result["links"]

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：common-app-context 直读（纯 HTTP，无需浏览器导航）。

        secUid 不落 cookie 且个人主页 SSR 在登录态下不稳定（实测），
        webapp 身份的唯一可靠来源是 app-context（SSR 或本接口）。
        """
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

        saved = await account_manager.save_owner(account.account_id, "tiktok", {"owner": owner})
        if saved is not None:
            logger.info("[%s] 身份信息已回填：%s(@%s)",
                        account.account_id, owner.get("nickname"), owner.get("unique_id"))


def _count_of(params: dict) -> int:
    """操作参数 count → [0, MAX_COUNT]，非法/缺省取 DEFAULT_COUNT。"""
    raw = str((params or {}).get("count") or "").strip()
    return (min(max(int(raw), 0), constants.MAX_COUNT)
            if raw.isdigit() else constants.DEFAULT_COUNT)
