"""Instagram 适配器：登录 / 登录态检查 / 收藏列表 API 直连 / 特别关注体系。

仅 API 直连（无浏览器模拟实现，method 入口保留供未来分发）；
接口细节与踩坑见 api_client.py 模块 docstring。
代理：instagram.com 需代理出网，与 threads 同策略（env → Windows 注册表）。
"""
import asyncio
import json
import logging
import re
import time

from app import config
from app.platforms.base import (
    AccountContext,
    ApiOperationParam,
    BasePlatformAdapter,
    FetchResult,
    FetchTarget,
    PARAM_CURSOR,
    PARAM_DATE_FROM,
    PARAM_DATE_TO,
)
from app.services import browser
from app.utils import now_iso
from . import api_client
from . import constants

logger = logging.getLogger("favapi.instagram")

DEFAULT_COUNT = 0   # 抓取数量缺省值：0 = 全部（用户反馈默认 20 反直觉）
MAX_COUNT = 1000
_USERNAME_RE = re.compile(constants.USERNAME_PATTERN)


class InstagramAdapter(BasePlatformAdapter):
    platform = constants.PLATFORM
    display_name = constants.DISPLAY_NAME
    home_url = constants.HOME_URL
    icon = "favicon.ico"
    implemented = True
    supported_actions = ("list_favorites",)
    api_fetch_implemented = True  # 收藏列表支持 API 直连（params.method="api"）
    follows_api_implemented = True  # 特别关注体系：关注列表 / 博主主页作品 / 播放 / 一键同步
    # 不填 count 默认抓全部（fetch_favorites_api 默认 0），覆盖通用 PARAM_COUNT 文案
    fetch_targets = (
        FetchTarget(
            action="list_favorites", name="抓取收藏列表",
            description="API 直连抓取收藏（已保存）帖子列表并入库",
            params=[
                ApiOperationParam(
                    key="count", label="抓取数量 (0 为全部)", type="number", placeholder="默认全部",
                    help="返回条数上限；留空或 0 抓取全部（结果以流式方式实时入库）",
                ),
                PARAM_CURSOR, PARAM_DATE_FROM, PARAM_DATE_TO,
            ],
        ),
    )

    def __init__(self, base_dir=None):
        self.base_dir = base_dir  # 图标目录（/platforms/{id}/icon 下发用）

    # ---------- 特别关注（follows）体系 ----------

    async def follows_profile_cookie(self, account: AccountContext) -> str:
        return await api_client.profile_cookie_header(account.profile_path)

    def follows_self_uid(self, cookie_header: str) -> str:
        # ds_user_id（REST v1 friendships 定位用；博主主键另用 username，见 follows_validate_uid）
        return api_client.self_user_id(cookie_header)

    def follows_validate_uid(self, sec_uid: str) -> None:
        if not _USERNAME_RE.match(str(sec_uid or "")):
            raise ValueError(
                "Instagram 博主 ID 需为用户名（主页地址 instagram.com/<用户名> 的最后一段）")

    async def follows_fetch_following(self, cookie_header: str, self_uid: str,
                                      count: int = 0, on_batch=None) -> tuple[list[dict], bool]:
        followings, has_more = await api_client.fetch_followings(
            cookie_header, self_uid, count, on_batch=on_batch)
        # 该接口不下发粉丝数与帖子数，置 None 由前端兜底展示
        mapped = [
            {
                "sec_uid": f["username"], "uid": f["pk"], "unique_id": f["username"],
                "nickname": f["full_name"] or f["username"], "signature": None,
                "avatar_url": f["avatar_url"], "follower_count": f["follower_count"],
                "aweme_count": None, "is_top": False,
            }
            for f in followings
        ]
        return mapped, has_more

    async def follows_fetch_posts_page(self, cookie_header: str, sec_uid: str,
                                       cursor: int | str = 0, count: int = 18) -> dict:
        # cursor 为服务端不透明游标 "{media_pk}_{user_pk}"（契约扩展 int|str 原样透传）：
        # 0/""/"0" = 首页，末页归 0（与 threads / 小红书同款）
        text = str(cursor or "").strip()
        after = "" if text in ("", "0") else text
        lsd = await asyncio.to_thread(api_client.fetch_lsd, cookie_header)
        batch = await asyncio.to_thread(
            api_client.fetch_user_posts_page, cookie_header, lsd, sec_uid, after,
            max(1, min(count, 50)),
        )
        batch["cursor"] = batch["cursor"] if batch["has_more"] else 0
        return batch

    async def follows_play_info(self, cookie_header: str, content_id: str) -> dict:
        media_id = str(content_id or "").strip()
        if not media_id.isdigit():
            raise ValueError("Instagram 作品 ID 需为纯数字媒体 pk")
        return await asyncio.to_thread(api_client.fetch_play_info, cookie_header, media_id)

    async def sync_author_posts(self, account: AccountContext, author_row: dict,
                                cookie_header: str, count: int) -> list[dict]:
        """拉取单博主最新 count 条帖子，回填 last_synced_at / uid / 昵称 / 头像。

        不负责入库：follows /sync 路由与 follow_sync 抓取目标（task 体系统一入库）共用本方法。
        """
        from app.database import db  # 延迟导入：平台层仅此方法触库
        from app.services import follow_store

        items, _ = await api_client.fetch_user_posts(cookie_header, author_row["sec_uid"], count)
        items = items[:count]  # 翻页按页边界返回可能超出，按 count 截断保证入库量一致
        author_id = next((it.get("author_id") for it in items if it.get("author_id")), None)
        author_name = next((it.get("author_name") for it in items if it.get("author_name")), None)
        # 作者头像：主帖 raw_data 的 user.profile_pic_url，作为库中无头像时的兜底
        avatar_url = None
        for it in items:
            try:
                raw = json.loads(it["raw_data"]) if isinstance(it.get("raw_data"), str) \
                    else (it.get("raw_data") or {})
            except (TypeError, ValueError):
                raw = {}
            url = str((raw.get("user") or {}).get("profile_pic_url") or "")
            if url.startswith("http"):
                avatar_url = url
                break
        await db.execute(
            """UPDATE follow_authors SET last_synced_at = ?,
                   uid = COALESCE(NULLIF(?, ''), uid),
                   nickname = COALESCE(NULLIF(?, ''), nickname),
                   avatar_url = COALESCE(NULLIF(?, ''), avatar_url)
               WHERE sec_uid = ?""",
            (now_iso(), author_id or "", author_name or "", avatar_url or "",
             author_row["sec_uid"]),
        )
        if follow_store.avatar_local_path(author_row["sec_uid"]) is None:
            source_url = (author_row.get("avatar_url") or "").strip() or avatar_url
            if source_url:
                await asyncio.to_thread(
                    follow_store.download_avatar, author_row["sec_uid"], source_url)
        return items

    # ---------- 登录 / 登录态 ----------

    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        """打开有头浏览器等待用户登录；检测到 sessionid 即成功。"""
        timeout = timeout or config.LOGIN_TIMEOUT
        deadline = time.monotonic() + timeout
        logger.info("[%s] 打开登录窗口，等待登录（最长 %ss）", account.account_id, timeout)
        async with browser.session(
            account.profile_path, headless=False, proxy=api_client.resolve_proxy()
        ) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(constants.HOME_URL, wait_until="domcontentloaded")
            checked = 0
            while time.monotonic() < deadline:
                cookies = await ctx.cookies()
                checked += 1
                if browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
                    logger.info("[%s] 第 %d 次轮询检测到登录 cookie，登录成功",
                                account.account_id, checked)
                    return True
                await asyncio.sleep(3)
            logger.warning("[%s] 等待登录超时（%ss，共轮询 %d 次），登录未完成",
                           account.account_id, timeout, checked)
            return False

    async def check_login_status(self, account: AccountContext) -> bool:
        """登录态检查：cookie 快速判定，cookie 存在即视为有效。

        服务端会话真实失效由抓取/操作时的 _check_auth 判定并抛 LoginExpiredError
        （执行器标记账号 expired）；网络异常向上抛（路由层 503），不误标。
        """
        async with browser.session(
            account.profile_path, headless=True, proxy=api_client.resolve_proxy()
        ) as ctx:
            cookies = await ctx.cookies(urls=[constants.HOME_URL])
        logged_in = browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS)
        logger.info("[%s] 登录态检查：%s", account.account_id, "有效" if logged_in else "无效")
        return logged_in

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：extra.instagram.owner = {id}。"""
        from app.services import account_manager  # 延迟导入避免循环依赖

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        owner = {"id": api_client.self_user_id(cookie_header)}
        saved = await account_manager.save_owner(
            account.account_id, constants.PLATFORM, {"owner": owner})
        if saved is not None:
            logger.info("[%s] 身份信息已回填：%s", account.account_id, owner["id"])

    # ---------- 收藏抓取 ----------

    async def fetch_favorites(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        # 浏览器模拟实现不存在，仅保留 API 直连；method 入口保留供未来平台分发
        self.resolve_fetch_method(params)
        return await self.fetch_favorites_api(account, params, on_batch)

    async def fetch_favorites_api(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        """API 直连：profile cookies + curl-impersonate Chrome 指纹请求 REST v1。

        cursor 语义与通用约定一致（已抓取条数偏移）；接口翻页内部用 next_max_id。
        """
        raw_count = params.get("count")
        # 不填默认 DEFAULT_COUNT=0 = 全部（用户反馈：默认 20 条反直觉）
        count = (DEFAULT_COUNT if raw_count in (None, "")
                 else max(0, min(int(raw_count), MAX_COUNT)))
        skip = max(0, int(params.get("cursor") or 0))
        logger.info("[%s] API 直连抓取收藏：count=%s cursor=%d",
                    account.account_id, count or "全部", skip)

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        collected, last_has_more = await api_client.fetch_saved(
            cookie_header, count=(count + skip) if count else 0, on_batch=on_batch
        )
        window = collected[skip:] if not count else collected[skip: skip + count]
        logger.info("[%s] API 直连抓取完成：共 %d 条，返回 [%d:%d] %d 条",
                    account.account_id, len(collected), skip, skip + len(window), len(window))
        return FetchResult(
            items=window,
            cursor=skip + len(window),
            has_more=last_has_more and (not count or len(collected) >= skip + count),
            total=len(collected),
        )
