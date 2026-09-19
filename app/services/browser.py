"""Playwright 浏览器会话管理：持久化 profile + 并发控制。

- 同一 profile 目录串行使用（asyncio Lock），避免两个浏览器实例写同一个 profile
- 全局并发上限（Semaphore），对应 PRD「初期单账号串行、多账号有限并发」
- shared_page：跨调用复用的常驻页面（空闲自动关闭），供签名需真实页面的
  页面通道高频使用（TikTok follows）
"""
import asyncio
import logging
import time
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
        context = await pw.chromium.launch_persistent_context(
            **_launch_options(profile_path, headless, proxy))
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


# ---------- 共享页面会话（跨调用复用，空闲自动关闭） ----------

# profile_key -> {pw, context, page, state, use_lock, closing, lock, close_task}
_shared_pages: dict[str, dict] = {}


def _launch_options(profile_path: str, headless: bool, proxy, user_agent=None) -> dict:
    path = Path(profile_path)
    path.mkdir(parents=True, exist_ok=True)
    options = {
        "user_data_dir": str(path),
        "headless": headless,
        # Playwright 1.49+ headless 默认用独立 headless_shell（未随手动安装提供），
        # channel="chromium" 让 headless 走完整 Chromium 的新 headless 模式。
        "channel": "chromium",
        "viewport": {"width": 1280, "height": 860},
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    # headless 下 UA 带 HeadlessChrome 标记且 Web Worker 里改不掉（站点 SDK 在
    # Worker 里采集环境做签名，会被风控识别）；user_agent 经 CDP
    # setUserAgentOverride 同时覆盖主世界与 Worker，传入正常 UA 即可隐藏
    if user_agent:
        options["user_agent"] = user_agent
    if proxy:
        options["proxy"] = {"server": proxy} if isinstance(proxy, str) else proxy
    return options


def _schedule_shared_close(key: str, ttl: float) -> None:
    """重排共享页面的空闲关闭任务（每次使用完毕后调用）。"""
    entry = _shared_pages.get(key)
    if not entry or entry["closing"]:
        return
    if entry["close_task"]:
        entry["close_task"].cancel()

    async def _close():
        await asyncio.sleep(ttl)
        e = _shared_pages.get(key)
        if e is not entry or e["closing"]:
            return
        e["closing"] = True  # 同步段置位：此后复用方一律走重建
        async with e["use_lock"]:  # 等正在使用的调用退出
            _shared_pages.pop(key, None)
            try:
                await e["context"].close()
            except Exception:
                logger.warning("共享页面上下文关闭异常（%s）", key, exc_info=True)
            finally:
                try:
                    await e["pw"].stop()
                finally:
                    e["lock"].release()  # 归还 profile 锁

    entry["close_task"] = asyncio.create_task(_close())


@asynccontextmanager
async def shared_page(profile_path: str, url: str, *, headless: bool = False,
                      proxy: dict | str | None = None, idle_ttl: float = 30.0,
                      user_agent: str | None = None, init=None):
    """获取/创建常驻共享页面（同 profile 复用同一 Chromium 实例），空闲 idle_ttl 秒后自动关闭。

    适用于「高频单页请求但签名需真实页面上下文」的场景（TikTok follows 页面
    通道）：避免每次请求冷启动浏览器（既是延迟也是风控扣分来源）。
    init(page) 仅在实例创建时执行一次（等签名 SDK / 校验登录态），返回值缓存到
    entry["state"]，与 page 一起以 (page, state) yield；init 抛异常时实例立即
    销毁并向上抛。user_agent 覆盖主世界与 Worker 的 UA（headless 隐藏用）。

    与 session() 共用同一把 profile 锁：实例存活期间锁由池持有，其他 session()
    调用排队等待（池空闲关闭后放行）；同一 page 的并发使用经 use_lock 串行化。
    """
    key = _profile_key(profile_path)
    entry = _shared_pages.get(key)
    if entry is not None and not entry["closing"] and not entry["page"].is_closed():
        entry["close_task"].cancel()  # 同步段：与 _close 的 closing 置位互斥
        async with entry["use_lock"]:
            try:
                yield entry["page"], entry["state"]
            finally:
                _schedule_shared_close(key, idle_ttl)
        return

    # 新建实例：拿 profile 锁（与 session 互斥），整个池生命周期持有不释放
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_BROWSERS)
    lock = _locks.setdefault(key, asyncio.Lock())
    await lock.acquire()
    try:
        async with _semaphore:
            pw = await async_playwright().start()
            context = await pw.chromium.launch_persistent_context(
                **_launch_options(profile_path, headless, proxy, user_agent))
            context.set_default_timeout(config.PAGE_TIMEOUT)
            page = await context.new_page()
            await page.goto(url, wait_until="commit", timeout=config.PAGE_TIMEOUT)
            try:
                state = await init(page) if init is not None else None
            except Exception:
                try:
                    await context.close()
                finally:
                    await pw.stop()
                raise
        entry = {
            "pw": pw, "context": context, "page": page, "state": state,
            "use_lock": asyncio.Lock(), "closing": False, "lock": lock,
            "close_task": None,
        }
        _shared_pages[key] = entry
    except Exception:
        lock.release()
        raise

    try:
        async with entry["use_lock"]:
            yield entry["page"], entry["state"]
    finally:
        _schedule_shared_close(key, idle_ttl)


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
