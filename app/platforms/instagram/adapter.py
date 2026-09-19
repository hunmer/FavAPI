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
    ApiOperation,
    ApiOperationParam,
    BasePlatformAdapter,
    FetchResult,
    FetchTarget,
    LoginExpiredError,
    PARAM_CURSOR,
    PARAM_DATE_FROM,
    PARAM_DATE_TO,
)
from app.services import browser
from app.utils import now_iso
from . import api_client
from . import constants
from .parser import parse_post_links

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
    download_api_implemented = True  # 支持按媒体 pk 解析下载直链（视频/图文/文案）
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
    api_operations = (
        ApiOperation(
            op_id="get_profile",
            name="获取登录用户信息",
            description="查询当前账号资料（用户名 / 昵称 / 头像 / 粉丝数 / 帖子数，只读）",
            params=(),
        ),
        ApiOperation(
            op_id="like_post",
            name="点赞帖子",
            description="API 直连点赞指定帖子（帖子详情页「赞」同款接口）",
            params=(
                ApiOperationParam(
                    key="media_id", label="帖子 ID", type="text", required=True,
                    placeholder="例如：3981703481130009879",
                    help="纯数字媒体 pk，可从收藏列表/博主作品条目的 content_id 获取",
                ),
            ),
        ),
        ApiOperation(
            op_id="unlike_post",
            name="取消点赞",
            description="API 直连取消指定帖子的点赞",
            params=(
                ApiOperationParam(
                    key="media_id", label="帖子 ID", type="text", required=True,
                    placeholder="例如：3981703481130009879",
                    help="纯数字媒体 pk（收藏列表/博主作品条目的 content_id）",
                ),
            ),
        ),
        ApiOperation(
            op_id="save_post",
            name="收藏帖子",
            description="API 直连收藏指定帖子（帖子详情页「收藏」同款接口）",
            params=(
                ApiOperationParam(
                    key="media_id", label="帖子 ID", type="text", required=True,
                    placeholder="例如：3981703481130009879",
                    help="纯数字媒体 pk（收藏列表/博主作品条目的 content_id）",
                ),
            ),
        ),
        ApiOperation(
            op_id="unsave_post",
            name="取消收藏",
            description="API 直连取消指定帖子的收藏（操作可逆，重新收藏即可恢复）",
            params=(
                ApiOperationParam(
                    key="media_id", label="帖子 ID", type="text", required=True,
                    placeholder="例如：3981703481130009879",
                    help="纯数字媒体 pk（收藏列表条目的 content_id）",
                ),
            ),
        ),
        ApiOperation(
            op_id="resolve_download_urls",
            name="解析下载直链",
            description="按帖子 ID 调详情接口返回可下载内容（视频/图文/文案，只读）",
            params=(
                ApiOperationParam(
                    key="post", label="帖子 ID", type="text", required=True,
                    placeholder="例如：3981703481130009879",
                    help="纯数字媒体 pk（收藏列表/博主作品条目的 content_id）",
                ),
            ),
        ),
    )

    def __init__(self, base_dir=None):
        self.base_dir = base_dir  # 图标目录（/platforms/{id}/icon 下发用）

    async def execute_api_operation(
        self, op_id: str, account: AccountContext, params: dict, on_event=None
    ) -> dict:
        if op_id == "get_profile":
            return await self._op_get_profile(account)
        if op_id in ("like_post", "unlike_post", "save_post", "unsave_post"):
            return await self._op_media_action(account, op_id, params)
        if op_id == "resolve_download_urls":
            source = str((params or {}).get("post") or "").strip()
            if not source:
                raise ValueError("请填写帖子 ID")
            return await self.resolve_download_urls(account, source)
        raise ValueError(f"未知操作：{op_id}")

    async def _op_get_profile(self, account: AccountContext) -> dict:
        """获取当前登录用户完整资料（users/{ds_user_id}/info）。"""
        logger.info("[%s] API 操作 get_profile", account.account_id)
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        profile = await asyncio.to_thread(api_client.fetch_viewer_profile, cookie_header)
        logger.info("[%s] get_profile：@%s（粉丝 %s，帖子 %s）", account.account_id,
                    profile.get("username"), profile.get("follower_count"),
                    profile.get("media_count"))
        return profile

    _MEDIA_ACTIONS = {
        "like_post": (api_client.like_media, "点赞"),
        "unlike_post": (api_client.unlike_media, "取消点赞"),
        "save_post": (api_client.save_media, "收藏"),
        "unsave_post": (api_client.unsave_media, "取消收藏"),
    }

    async def _op_media_action(self, account: AccountContext, op_id: str,
                               params: dict) -> dict:
        """媒体写操作（点赞 / 取消点赞 / 收藏 / 取消收藏，/api/graphql mutation）。"""
        media_id = str((params or {}).get("media_id") or "").strip()
        if not media_id.isdigit():
            raise ValueError("请填写帖子 ID（纯数字媒体 pk）")
        fn, label = self._MEDIA_ACTIONS[op_id]
        logger.info("[%s] API 操作 %s：%s", account.account_id, op_id, media_id)
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        # actor_id（fbid_v2）与写令牌（fb_dtsg/lsd）每次操作现取，不缓存
        profile = await asyncio.to_thread(api_client.fetch_viewer_profile, cookie_header)
        actor_id = profile.get("fbid_v2") or ""
        if not actor_id:
            raise RuntimeError("未能获取当前用户 fbid_v2（写 mutation 的 actor_id）")
        tokens = await asyncio.to_thread(api_client.fetch_tokens, cookie_header)
        data = await asyncio.to_thread(fn, cookie_header, tokens, actor_id, media_id)
        logger.info("[%s] %s完成：%s", account.account_id, label, media_id)
        return {"media_id": media_id, "status": "ok", "response": data}

    async def resolve_download_urls(self, account: AccountContext, content_id: str) -> list[dict]:
        """按媒体 pk 调详情接口返回可下载内容列表（首项为推荐下载项）。

        content_id 为纯数字媒体 pk（收藏列表 / 博主作品条目的 content_id）；
        CDN 直链（scontent-*.cdninstagram.com）实测仅 UA 即可下载，交给 aria2c
        时作为请求头注入。
        """
        media_id = str(content_id or "").strip()
        if not media_id.isdigit():
            raise ValueError("Instagram 下载解析需要纯数字媒体 pk（条目的 content_id）")
        headers = {
            "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
        }
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        logger.info("[%s] 解析下载直链：%s", account.account_id, media_id)
        media = await asyncio.to_thread(api_client.fetch_media_info, cookie_header, media_id)
        links = parse_post_links(media)
        if not any(l.get("url") for l in links):
            # 纯文字帖只有文案链接，无直链不算失败；完全为空才视为异常
            if not any(l.get("kind") == "text" for l in links):
                raise RuntimeError("帖子详情无可下载内容（帖子可能已删除或设为私密）")
        user = media.get("user") or {}
        for link in links:
            if link.get("url"):
                link["headers"] = headers
            # 作者信息随链接下发：下载分类模板 {authorName}/{authorId} 变量来源
            link.setdefault("author_name", user.get("username"))
            link.setdefault("author_id", str(user.get("pk") or ""))
        return links

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
        """登录态检查：cookie 快速判定 + users/info 真实校验。

        cookie 缺失直接 False；cookie 存在但服务端会话已被踢（sessionid 失效）
        由 fetch_viewer_profile 判定。风控挑战（InstagramChallengeError）与网络
        异常向上抛（路由层 503），不误标 expired。
        """
        logged_in, _ = await self._check_and_maybe_refresh(account, refresh=False)
        return logged_in

    async def check_login_status_and_refresh(self, account: AccountContext) -> tuple[bool, bool]:
        """单会话版本：一次读 cookie + 一次 API 校验，登录有效时身份已随响应拿到，直接回填。"""
        return await self._check_and_maybe_refresh(account, refresh=True)

    async def _check_and_maybe_refresh(self, account: AccountContext, refresh: bool) -> tuple[bool, bool]:
        async with browser.session(
            account.profile_path, headless=True, proxy=api_client.resolve_proxy()
        ) as ctx:
            cookies = await ctx.cookies(urls=[constants.HOME_URL])
        if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
            logger.info("[%s] 登录态检查：无效（profile 无登录 cookie）", account.account_id)
            return False, False
        cookie_header = "; ".join(
            f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
        try:
            profile = await asyncio.to_thread(
                api_client.fetch_viewer_profile, cookie_header)
        except LoginExpiredError:
            logger.warning("[%s] 登录态检查：cookie 存在但服务端会话已失效", account.account_id)
            return False, False
        logger.info("[%s] 登录态检查：有效（@%s）", account.account_id, profile.get("username"))
        if not refresh:
            return True, False
        try:
            await self._save_owner(account, profile)
            return True, True
        except Exception:
            logger.warning("[%s] 身份回填失败（不影响登录态结论）", account.account_id, exc_info=True)
            return True, False

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：extra.instagram.owner = {id, username, avatar, ...}。"""
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        profile = await asyncio.to_thread(api_client.fetch_viewer_profile, cookie_header)
        await self._save_owner(account, profile)

    async def _save_owner(self, account: AccountContext, profile: dict) -> None:
        from app.services import account_manager  # 延迟导入避免循环依赖

        owner = {
            "id": profile["id"],
            "fbid_v2": profile.get("fbid_v2"),
            "username": profile.get("username"),
            "full_name": profile.get("full_name"),
            "avatar": profile.get("avatar"),  # 带签名 CDN 原链，save_owner 落盘防过期
            "follower_count": profile.get("follower_count"),
            "media_count": profile.get("media_count"),
        }
        saved = await account_manager.save_owner(account.account_id, constants.PLATFORM, {"owner": owner})
        if saved is not None:
            logger.info("[%s] 身份信息已回填：@%s(%s)",
                        account.account_id, profile.get("username"), profile["id"])

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
