"""Playwright 浏览器会话管理：持久化 profile + 并发控制。

- 同一 profile 目录串行使用（asyncio Lock），避免两个浏览器实例写同一个 profile
- 全局并发上限（Semaphore），对应 PRD「初期单账号串行、多账号有限并发」
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import async_playwright

from app import config

_locks: dict[str, asyncio.Lock] = {}
_semaphore: asyncio.Semaphore | None = None


def has_login_cookies(cookies: list[dict], keys: tuple[str, ...]) -> bool:
    """任一关键 cookie 存在且非空即视为已登录。"""
    by_name = {c.get("name"): c.get("value") for c in cookies or []}
    return any(by_name.get(k) for k in keys)


def is_busy(profile_path: str) -> bool:
    """该 profile 当前是否有浏览器会话在执行（登录/抓取中）。"""
    lock = _locks.get(str(Path(profile_path).resolve()).lower())
    return bool(lock and lock.locked())


@asynccontextmanager
async def session(profile_path: str, headless: bool | None = None):
    """以持久化 profile 打开 Chromium，退出时关闭。

    用法: async with browser.session(path) as ctx: ...
    """
    headless = config.HEADLESS if headless is None else headless
    path = Path(profile_path)
    path.mkdir(parents=True, exist_ok=True)

    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_BROWSERS)

    lock = _locks.setdefault(str(path.resolve()).lower(), asyncio.Lock())
    async with lock, _semaphore:
        pw = await async_playwright().start()
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(path),
            headless=headless,
            viewport={"width": 1280, "height": 860},
            args=["--disable-blink-features=AutomationControlled"],
        )
        context.set_default_timeout(config.PAGE_TIMEOUT)
        try:
            yield context
        finally:
            try:
                await context.close()
            finally:
                await pw.stop()
