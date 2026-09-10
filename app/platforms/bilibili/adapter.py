"""Bilibili 适配器：扫码登录 / 收藏列表抓取（收藏夹公开接口分页请求）。

与抖音的响应拦截 + 滚动不同，Bilibili 收藏夹有干净的分页接口
（fav/resource/list 的 pn/ps），无需打开页面点击按钮：
直接用浏览器上下文发 API 请求，自动携带 profile 登录态与 UA，降低风控概率。
"""
import asyncio
import json
import logging
import time

from app import config
from app.platforms.base import (
    AccountContext,
    BasePlatformAdapter,
    FetchResult,
    LoginExpiredError,
)
from app.services import browser
from . import constants
from .parser import extract_mid, parse_folder_list, parse_resource_list

logger = logging.getLogger("favapi.bilibili")


class BilibiliAdapter(BasePlatformAdapter):
    platform = constants.PLATFORM
    display_name = constants.DISPLAY_NAME
    implemented = True
    supported_actions = ("list_favorites",)

    def validate_params(self, params: dict) -> None:
        raw_url = str(params.get("url") or "").strip()
        raw_mid = str(params.get("mid") or "").strip()
        if not raw_url and not raw_mid:
            return  # 未指定 → 默认抓当前登录用户自己的收藏夹
        mid = extract_mid(raw_url) or raw_mid
        if not (mid and mid.isdigit()):
            raise ValueError(
                "目标用户无效：url 需为 "
                "https://space.bilibili.com/{用户id}/favlist 形式的收藏夹主页链接，"
                "或 mid 传纯数字用户 id；留空则默认当前登录用户"
            )

    @staticmethod
    def _target_mid(params: dict) -> str:
        return extract_mid(str(params.get("url") or "")) or str(params.get("mid") or "").strip()

    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        """打开有头浏览器等待扫码；检测到 SESSDATA 即成功。"""
        timeout = timeout or config.LOGIN_TIMEOUT
        deadline = time.monotonic() + timeout
        logger.info("[%s] 打开登录窗口，等待扫码（最长 %ss）", account.account_id, timeout)
        async with browser.session(account.profile_path, headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(constants.HOME_URL, wait_until="domcontentloaded")
            checked = 0
            while time.monotonic() < deadline:
                cookies = await ctx.cookies()
                checked += 1
                if browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
                    logger.info("[%s] 第 %d 次轮询检测到登录 cookie，登录成功", account.account_id, checked)
                    return True
                await asyncio.sleep(3)
            logger.warning("[%s] 等待扫码超时（%ss，共轮询 %d 次），登录未完成", account.account_id, timeout, checked)
            return False

    async def check_login_status(self, account: AccountContext) -> bool:
        """登录态检查：仅读取 profile cookie，不导航页面 → 固定无头。"""
        async with browser.session(account.profile_path, headless=True) as ctx:
            cookies = await ctx.cookies()
            ok = browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS)
            logger.info("[%s] 登录态检查：%s", account.account_id, "有效" if ok else "无效")
            return ok

    async def fetch_favorites(
        self, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        self.validate_params(params)
        mid = self._target_mid(params)
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        # count=0 表示不设条数上限，翻完所有收藏夹所有页
        target = skip + count if count else None
        media_id = str(params.get("media_id") or "").strip()  # 可选：只抓指定收藏夹
        raw_interval = params.get("interval_ms")
        interval_ms = (
            constants.PAGE_INTERVAL_MS if raw_interval in (None, "")
            else max(0, min(int(raw_interval), 10000))  # 可选：翻页请求间隔（ms）
        )
        logger.info(
            "[%s] 开始抓取收藏夹：mid=%s count=%s cursor=%d media_id=%s interval=%dms",
            account.account_id, mid or "当前登录用户", count or "全部", skip,
            media_id or "全部", interval_ms,
        )

        items: list[dict] = []
        seen: set[tuple[str, str]] = set()  # (content_id, media_id)：同一视频收藏在多个夹各记一条
        owner: dict = {}
        folders_meta: list[dict] = []
        stopped_early = False

        async with browser.session(account.profile_path, headless=config.HEADLESS) as ctx:
            if not mid:
                cookies = await ctx.cookies()
                mid = next(
                    (c["value"] for c in cookies if c.get("name") == "DedeUserID" and c.get("value")),
                    "",
                )
                if not mid:
                    raise LoginExpiredError(
                        "未指定目标用户，且账号未登录（Bilibili cookie 中无 DedeUserID）："
                        "请先扫码登录，或在参数中传入收藏夹主页 URL / 用户 id"
                    )
                logger.info("[%s] 未指定用户，默认当前登录用户 mid=%s", account.account_id, mid)
            headers = {"Referer": f"https://space.bilibili.com/{mid}/favlist"}

            if media_id:
                targets = [{"media_id": media_id, "title": None, "media_count": None}]
            else:
                data = await self._api_get(
                    ctx, constants.FAV_FOLDER_LIST_API, {"up_mid": mid}, headers
                )
                parsed = parse_folder_list(data)
                owner = parsed["owner"]
                folders_meta = parsed["folders"]
                targets = folders_meta
                logger.info(
                    "[%s] 用户 %s 共 %d 个收藏夹：%s",
                    account.account_id, mid, len(targets),
                    ", ".join(f"{f['title']}({f['media_count']})" for f in targets) or "无",
                )

            for folder in targets:
                pn = 1
                while True:
                    data = await self._api_get(
                        ctx, constants.FAV_RESOURCE_LIST_API,
                        {
                            "media_id": folder["media_id"], "pn": pn, "ps": constants.PAGE_SIZE,
                            "keyword": "", "order": "mtime", "type": 0, "tid": 0, "platform": "web",
                        },
                        headers,
                    )
                    batch = parse_resource_list(data)
                    if batch["owner"].get("name"):
                        owner = batch["owner"]  # resource/list 的 upper 信息最全
                    if media_id and not folders_meta:
                        folders_meta = [batch["favorite"]]
                    if folder["title"] is None:
                        folder["title"] = batch["favorite"]["title"]

                    new_count = 0
                    page_items: list[dict] = []
                    for it in batch["items"]:
                        key = (it["content_id"], folder["media_id"])
                        if key not in seen:
                            seen.add(key)
                            it["fav_media_id"] = folder["media_id"]
                            it["fav_title"] = folder["title"] or ""
                            items.append(it)
                            page_items.append(it)
                            new_count += 1
                    logger.info(
                        "[%s] 收藏夹「%s」第 %d 页：%d 条（新增 %d，累计去重 %d），has_more=%s",
                        account.account_id, folder["title"] or folder["media_id"], pn,
                        len(batch["items"]), new_count, len(items), batch["has_more"],
                    )
                    if on_batch and page_items:
                        await on_batch({
                            "folder": {"media_id": folder["media_id"], "title": folder["title"]},
                            "page": pn,
                            "items": page_items,
                            "total_fetched": len(items),
                        })

                    if not batch["has_more"]:
                        break  # 该收藏夹已到底
                    if target is not None and len(items) >= target:
                        stopped_early = True
                        break  # 已凑够窗口，该夹仍有剩余
                    if pn >= constants.MAX_PAGES:
                        logger.warning("单收藏夹翻页达上限 %d 页，提前结束", constants.MAX_PAGES)
                        stopped_early = True
                        break
                    pn += 1
                    await asyncio.sleep(interval_ms / 1000)
                if stopped_early:
                    break

        window = items[skip:] if target is None else items[skip:target]
        meta = {"owner": owner, "folders": folders_meta}
        await self._save_owner(account.account_id, meta)
        logger.info(
            "[%s] 抓取完成：去重 %d 条，返回 [%d:%d] 共 %d 条，has_more=%s，主人=%s(%s)",
            account.account_id, len(items), skip, skip + len(window), len(window),
            stopped_early, owner.get("name"), owner.get("mid"),
        )
        return FetchResult(
            items=window,
            cursor=skip + len(window),
            has_more=stopped_early,
            total=sum(f.get("media_count") or 0 for f in folders_meta),
            meta=meta,
        )

    async def _api_get(self, ctx, url: str, params: dict, headers: dict) -> dict:
        """通过浏览器上下文请求 Bilibili 接口；非 0 code 抛异常（任务记 failed）。"""
        resp = await ctx.request.get(url, params=params, headers=headers)
        if not resp.ok:
            raise RuntimeError(f"Bilibili 接口请求失败 HTTP {resp.status}，可能被风控拦截，请稍后重试")
        data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"Bilibili 接口错误 code={data.get('code')}：{data.get('message') or data.get('msg')}"
            )
        return data.get("data") or {}

    async def _save_owner(self, account_id: str, meta: dict):
        """记录收藏夹主人信息到账号 extra（延迟导入避免循环依赖）。"""
        owner = meta.get("owner") or {}
        if not owner.get("mid"):
            return
        from app.services import account_manager

        row = await account_manager.get_account(account_id)
        if row is None:
            return
        extra = row.get("extra") or {}
        extra["bilibili"] = {"owner": owner, "folders": meta.get("folders") or []}
        await account_manager.update_account(
            account_id, extra=json.dumps(extra, ensure_ascii=False)
        )
