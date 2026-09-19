"""YouTube 播放列表页面适配器（解析 feed/playlists 的 DOM 分组）。

特别关注（follows）体系走 InnerTube API 直连（见 api_client.py）：
订阅列表 browse FEchannels（SAPISIDHASH）+ 频道 Videos tab browse +
player 详情；播放用官方 embed iframe（WEB 直链绑定 PO token 会话不可独立访问）。
"""
import json
import re
import asyncio
import logging

from app import config
from app.platforms.base import BasePlatformAdapter, FetchResult, AccountContext, LoginExpiredError
from app.services import browser
from app.utils import now_iso
from . import api_client

logger = logging.getLogger("favapi.youtube")


class YouTubeAdapter(BasePlatformAdapter):
    platform = "youtube"
    display_name = "YouTube"
    home_url = "https://www.youtube.com/feed/playlists"
    playlist_url = "https://www.youtube.com/playlist?list=LL"
    icon = "favicon.ico"
    supported_actions = ("list_favorites",)
    follows_api_implemented = True

    _COOKIE_KEYS = ("SID", "SAPISID", "__Secure-3PSID", "LOGIN_INFO")

    def __init__(self, base_dir=None):
        self.base_dir = base_dir

    async def login(self, account: AccountContext, timeout=None) -> bool:
        import time
        timeout = timeout or config.LOGIN_TIMEOUT
        deadline = time.monotonic() + timeout
        async with browser.session(account.profile_path, headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(self.home_url, wait_until="domcontentloaded")
            while time.monotonic() < deadline:
                if browser.has_login_cookies(await ctx.cookies(), self._COOKIE_KEYS):
                    return True
                await page.wait_for_timeout(3000)
        return False

    async def check_login_status(self, account: AccountContext) -> bool:
        async with browser.session(account.profile_path, headless=True) as ctx:
            return browser.has_login_cookies(await ctx.cookies(), self._COOKIE_KEYS)

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：首页右上角头像按钮 DOM（img.alt=频道名）。"""
        async with browser.session(account.profile_path, headless=True) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
            try:
                await page.wait_for_selector("#avatar-btn img", timeout=10_000)
            except Exception:
                logger.info("[%s] 首页无头像按钮（可能未登录），跳过身份回填", account.account_id)
                return
            info = await page.evaluate(
                """() => {
                    const img = document.querySelector('#avatar-btn img');
                    return img ? {name: img.alt, avatar: img.src} : null;
                }"""
            )
        if not info:
            return
        owner = {"name": info.get("name"), "avatar": info.get("avatar")}
        from app.services import account_manager  # 延迟导入避免循环依赖

        saved = await account_manager.save_owner(account.account_id, "youtube", {"owner": owner})
        if saved is not None:
            logger.info("[%s] 身份信息已回填：%s", account.account_id, owner.get("name"))

    async def fetch_favorites(self, account: AccountContext, params: dict, on_batch=None) -> FetchResult:
        target = int(params.get("count") or 0)
        logger.info("[%s] YouTube 喜欢的视频抓取开始：url=%s count=%s",
                    account.account_id, self.playlist_url, target or "全部")
        items = []
        async with browser.session(account.profile_path, headless=config.HEADLESS) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(self.playlist_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            for _ in range(20):
                rows = await page.locator("#contents yt-lockup-view-model").evaluate_all("""els => els.map(el => {
                    const host = el.querySelector('[class*="content-id-"]') || el;
                    const id = (host.className || '').match(/content-id-([^ ]+)/)?.[1] || '';
                    const titleEl = el.querySelector('h3, [class*="Title"]');
                    const link = el.querySelector('a[href*="watch?v="]');
                    const author = el.querySelector('a[href*="/channel/"]');
                    const image = el.querySelector('img');
                    const imageUrl = image?.currentSrc || image?.src || image?.getAttribute('data-thumb') || image?.getAttribute('data-src') || image?.getAttribute('srcset')?.split(',')[0]?.trim().split(' ')[0] || '';
                    const duration = el.querySelector('[aria-label*="minute"], [aria-label*="second"]');
                    return {id, title: titleEl?.textContent?.trim() || '', url: link?.href || '',
                        author: author?.textContent?.trim() || '', image: imageUrl,
                        duration: duration?.getAttribute('aria-label') || ''};
                })""")
                fresh = []
                for row in rows:
                    if target and len(items) >= target:
                        break
                    content_id = str(row.get("id") or "")
                    if not content_id or any(i["content_id"] == content_id for i in items):
                        continue
                    item = {"content_id": content_id, "title": row.get("title") or None,
                            "description": None, "author_name": row.get("author") or None,
                            "cover_url": row.get("image") or f"https://i.ytimg.com/vi/{content_id}/hqdefault.jpg",
                            "raw_data": json.dumps(row, ensure_ascii=False)}
                    items.append(item); fresh.append(item)
                if fresh and on_batch:
                    await on_batch({"page": len(items), "items": fresh})
                if target and len(items) >= target:
                    break
                await page.mouse.wheel(0, 2400)
                await page.wait_for_timeout(1800)
            if not browser.has_login_cookies(await ctx.cookies(), self._COOKIE_KEYS):
                raise LoginExpiredError("YouTube 登录态缺失")
        items = items[:target] if target else items
        logger.info("[%s] YouTube 喜欢的视频抓取完成：items=%d", account.account_id, len(items))
        return FetchResult(items=items, total=len(items), has_more=False)

    # ---------- 特别关注（follows）体系：InnerTube API 直连 ----------

    async def follows_profile_cookie(self, account: AccountContext) -> str:
        return await api_client.profile_cookie_header(account.profile_path)

    def follows_self_uid(self, cookie_header: str) -> str:
        return api_client.fetch_self_channel_id(cookie_header)

    def follows_validate_uid(self, sec_uid: str) -> None:
        if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", str(sec_uid or "")):
            raise ValueError("YouTube 博主主键需为 UC 开头的 24 位频道 ID")

    async def follows_fetch_following(self, cookie_header: str, self_uid: str,
                                      count: int = 0, on_batch=None) -> tuple[list[dict], bool]:
        # 订阅 feed（FEchannels）按会话返回，self_uid 不参与请求
        return await api_client.fetch_subscriptions(cookie_header, count, on_batch=on_batch)

    async def follows_fetch_posts_page(self, cookie_header: str, sec_uid: str,
                                       cursor: int | str = 0, count: int = 18) -> dict:
        # cursor 为 InnerTube continuation token（str，0/空 = 首页）；末页归 0 对齐统一语义
        batch = await asyncio.to_thread(
            api_client.fetch_channel_videos_page, cookie_header, sec_uid, str(cursor or ""))
        return {
            "items": batch["items"][:max(1, count)] if count else batch["items"],
            "cursor": batch["continuation"] or 0,
            "has_more": bool(batch["continuation"]),
        }

    async def follows_play_info(self, cookie_header: str, content_id: str) -> dict:
        # YouTube WEB 直链绑定 PO token 生成会话（客户端独立访问 403），
        # video_urls 留空、下发官方 embed 的 iframe_url 由前端 <iframe> 播放
        return await asyncio.to_thread(api_client.fetch_video_play_info, cookie_header, content_id)

    async def sync_author_posts(self, account: AccountContext, author_row: dict,
                                cookie_header: str, count: int) -> list[dict]:
        """拉取单博主最新 count 条视频并回填 last_synced_at / uid / 昵称。

        不负责入库：follows /sync 路由与 follow_sync 抓取目标共用本方法。
        """
        from app.database import db  # 延迟导入：平台层仅此方法触库
        from app.services import follow_store

        items, _ = await api_client.fetch_channel_videos(
            cookie_header, author_row["sec_uid"], count)
        items = items[:count]  # 单页固定 30 条，按 count 截断保证入库量与配置一致
        author_id = next((it.get("author_id") for it in items if it.get("author_id")), None)
        author_name = next((it.get("author_name") for it in items if it.get("author_name")), None)
        await db.execute(
            """UPDATE follow_authors SET last_synced_at = ?,
                   uid = COALESCE(NULLIF(?, ''), uid),
                   nickname = COALESCE(NULLIF(?, ''), nickname)
               WHERE sec_uid = ?""",
            (now_iso(), author_id or "", author_name or "", author_row["sec_uid"]),
        )
        # Videos tab 不带作者头像：本地文件缺失时按库中 URL（关注列表入库）补下自愈
        if follow_store.avatar_local_path(author_row["sec_uid"]) is None:
            source_url = (author_row.get("avatar_url") or "").strip()
            if source_url:
                await asyncio.to_thread(
                    follow_store.download_avatar, author_row["sec_uid"], source_url
                )
        return items
