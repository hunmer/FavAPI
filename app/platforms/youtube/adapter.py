"""YouTube 播放列表页面适配器（解析 feed/playlists 的 DOM 分组）。"""
import json
import asyncio
import uuid

from app import config
from app.platforms.base import BasePlatformAdapter, FetchResult, AccountContext, LoginExpiredError
from app.services import browser
from app.services.download_worker import _resolve_command, _write_cookies_file


class YouTubeAdapter(BasePlatformAdapter):
    platform = "youtube"
    display_name = "YouTube"
    home_url = "https://www.youtube.com/feed/playlists"
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
        base = _resolve_command("yt-dlp")
        if base is None:
            raise RuntimeError("未找到 yt-dlp，请先安装：pip install -U yt-dlp")
        cookie_id = f"youtube_{uuid.uuid4().hex}"
        cookies_file = await _write_cookies_file(cookie_id, account.account_id, "youtube")
        if cookies_file is None:
            raise LoginExpiredError("YouTube Cookies 不存在，请先完成登录")
        cmd = [*base, "--flat-playlist", "--dump-single-json", "--skip-download", self.home_url,
               "--cookies", str(cookies_file)]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=config.FETCH_TIMEOUT)
            if proc.returncode:
                raise RuntimeError(f"yt-dlp 获取播放列表失败：{err.decode(errors='replace')[-500:]}")
            data = json.loads(out.decode("utf-8", errors="replace"))
        finally:
            cookies_file.unlink(missing_ok=True)
        items = []
        for row in data.get("entries") or []:
            content_id = str(row.get("id") or "")
            if not content_id or any(i["content_id"] == content_id for i in items):
                continue
            item = {
                "content_id": content_id,
                "title": row.get("title") or None,
                "description": row.get("description") or None,
                "author_name": row.get("uploader") or row.get("channel") or None,
                "cover_url": row.get("thumbnail") or None,
                "raw_data": json.dumps(row, ensure_ascii=False),
            }
            items.append(item)
        if target:
            items = items[:target]
        if on_batch and items:
            await on_batch({"page": len(items), "items": items})
        return FetchResult(items=items, total=len(items), has_more=False)
