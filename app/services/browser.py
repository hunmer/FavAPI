"""Playwright 浏览器会话管理：持久化 profile + 并发控制。

- 同一 profile 目录串行使用（asyncio Lock），避免两个浏览器实例写同一个 profile
- 全局并发上限（Semaphore），对应 PRD「初期单账号串行、多账号有限并发」
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import async_playwright

from app import config

logger = logging.getLogger("favapi.browser")

_locks: dict[str, asyncio.Lock] = {}
_semaphore: asyncio.Semaphore | None = None

# 手动浏览会话（账号详情页【打开浏览器】）：account_id -> 持久任务，不自动关闭
_manual_tasks: dict[str, asyncio.Task] = {}


def has_login_cookies(cookies: list[dict], keys: tuple[str, ...]) -> bool:
    """任一关键 cookie 存在且非空即视为已登录。"""
    by_name = {c.get("name"): c.get("value") for c in cookies or []}
    return any(by_name.get(k) for k in keys)


def is_busy(profile_path: str) -> bool:
    """该 profile 当前是否有浏览器会话在执行（登录/抓取中）。"""
    lock = _locks.get(str(Path(profile_path).resolve()).lower())
    return bool(lock and lock.locked())


@asynccontextmanager
async def session(profile_path: str, headless: bool | None = None, proxy: dict | str | None = None):
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
        launch_options = {
            "user_data_dir": str(path),
            "headless": headless,
            "viewport": {"width": 1280, "height": 860},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        # Playwright 不会自动继承系统代理；调用方可显式传入 server / username / password。
        if proxy:
            launch_options["proxy"] = {"server": proxy} if isinstance(proxy, str) else proxy
        context = await pw.chromium.launch_persistent_context(
            **launch_options,
        )
        context.set_default_timeout(config.PAGE_TIMEOUT)
        try:
            yield context
        finally:
            try:
                await context.close()
            finally:
                await pw.stop()


# ---------- 手动浏览（不自动关闭，供账号详情页人工操作） ----------

def is_manual_open(account_id: str) -> bool:
    task = _manual_tasks.get(account_id)
    return bool(task and not task.done())


async def open_manual(account_id: str, profile_path: str, url: str) -> dict:
    """打开手动浏览窗口；已在打开状态则切换为关闭（toggle）。返回 {opened, closed?}。"""
    if is_manual_open(account_id):
        return await close_manual(account_id)

    async def _hold():
        try:
            async with session(profile_path, headless=False) as ctx:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                closed = asyncio.Event()
                ctx.on("close", closed.set)
                await closed.wait()  # 用户手动关闭浏览器窗口
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("手动浏览器会话异常（%s）", account_id)
        finally:
            _manual_tasks.pop(account_id, None)

    _manual_tasks[account_id] = asyncio.create_task(_hold())
    logger.info("[%s] 手动浏览器已打开（不会自动关闭）", account_id)
    return {"opened": True}


async def close_manual(account_id: str) -> dict:
    """关闭手动浏览窗口；登录/抓取发起前也会调用让位。返回 {opened: False, closed}。"""
    task = _manual_tasks.get(account_id)
    if not task or task.done():
        _manual_tasks.pop(account_id, None)
        return {"opened": False, "closed": False}
    task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=15)
    except Exception:
        pass
    _manual_tasks.pop(account_id, None)
    logger.info("[%s] 手动浏览器已关闭", account_id)
    return {"opened": False, "closed": True}
