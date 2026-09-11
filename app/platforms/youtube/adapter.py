"""YouTube 播放列表页面适配器（解析 feed/playlists 的 DOM 分组）。"""
import json
import asyncio
import logging

from app import config
from app.platforms.base import BasePlatformAdapter, FetchResult, AccountContext, LoginExpiredError
from app.services import browser

logger = logging.getLogger("favapi.youtube")


class YouTubeAdapter(BasePlatformAdapter):
    platform = "youtube"
    display_name = "YouTube"
    home_url = "https://www.youtube.com/feed/playlists"
    playlist_url = "https://www.youtube.com/playlist?list=LL"
    icon = "favicon.ico"
    supported_actions = ("list_favorites",)

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
