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
# 手动会话当前 page（【账号打开】在已开会话内导航复用）
_manual_pages: dict[str, object] = {}

# 当前活跃的 profile 会话（登录/抓取）：resolved profile -> {context, headless}
# 【账号打开】遇占用时在可见会话内开新 tab 复用
_active_sessions: dict[str, dict] = {}


def _profile_key(profile_path: str) -> str:
    return str(Path(profile_path).resolve()).lower()


def has_login_cookies(cookies: list[dict], keys: tuple[str, ...]) -> bool:
    """任一关键 cookie 存在且非空即视为已登录（名称大小写不敏感）。"""
    by_name = {str(c.get("name") or "").lower(): c.get("value") for c in cookies or []}
    return any(by_name.get(str(k).lower()) for k in keys)


def is_busy(profile_path: str) -> bool:
    """该 profile 当前是否有浏览器会话在执行（登录/抓取中）。"""
    lock = _locks.get(_profile_key(profile_path))
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

    lock = _locks.setdefault(_profile_key(profile_path), asyncio.Lock())
    async with lock, _semaphore:
        pw = await async_playwright().start()
        launch_options = {
            "user_data_dir": str(path),
            "headless": headless,
            # Playwright 1.49+ headless 默认用独立 headless_shell（未随手动安装提供），
            # channel="chromium" 让 headless 走完整 Chromium 的新 headless 模式。
            "channel": "chromium",
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
        session_key = _profile_key(profile_path)
        _active_sessions[session_key] = {"context": context, "headless": headless}
        try:
            yield context
        finally:
            _active_sessions.pop(session_key, None)
            try:
                await context.close()
            finally:
                await pw.stop()


def open_tab(profile_path: str, url: str) -> dict | None:
    """在占用中的可见（非 headless）会话里同步开新标签页导航到 url。

    供【账号打开】在登录/抓取占用 profile 时复用已开窗口；无头会话或未占用返回 None。
    注意：新 tab 随占用会话结束一并关闭。
    """
    session = _active_sessions.get(_profile_key(profile_path))
    if not session or session["headless"]:
        return None

    async def _open():
        page = await session["context"].new_page()
        await page.goto(url, wait_until="domcontentloaded")
        page.bring_to_front()

    # 在占用方的 event loop（本服务同一 loop）上起任务，不等待其释放 profile 锁
    task = asyncio.create_task(_open())
    task.add_done_callback(lambda t: t.exception() and logger.warning("占用会话新开标签页失败：%s", t.exception()))
    return {"opened": True, "tab": True}


# ---------- 手动浏览（不自动关闭，供账号详情页人工操作） ----------

def is_manual_open(account_id: str) -> bool:
    task = _manual_tasks.get(account_id)
    return bool(task and not task.done())


async def open_manual(account_id: str, profile_path: str, url: str, *, navigate_if_open: bool = False) -> dict:
    """打开手动浏览窗口；已在打开状态时默认切换为关闭（toggle）。

    navigate_if_open=True 时已打开则导航到 url 而不关闭（数据浏览卡片【账号打开】）。
    返回 {opened, closed?, navigated?}。
    """
    if is_manual_open(account_id):
        if navigate_if_open:
            page = _manual_pages.get(account_id)
            if page is not None and not page.is_closed():
                await page.goto(url, wait_until="domcontentloaded")
                return {"opened": True, "navigated": True}
            await close_manual(account_id)  # page 引用丢失，关闭后走重开流程
        else:
            return await close_manual(account_id)

    async def _hold():
        try:
            async with session(profile_path, headless=False) as ctx:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                _manual_pages[account_id] = page
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
            _manual_pages.pop(account_id, None)

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
