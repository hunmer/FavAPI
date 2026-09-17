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
    ApiOperation,
    ApiOperationParam,
    BasePlatformAdapter,
    FetchResult,
    LoginExpiredError,
)
from app.services import browser
from app.utils import parse_date_window
from . import api_client
from . import constants
from .parser import extract_mid, parse_folder_list, parse_resource_list

logger = logging.getLogger("favapi.bilibili")


class BilibiliAdapter(BasePlatformAdapter):
    platform = constants.PLATFORM
    display_name = constants.DISPLAY_NAME
    home_url = constants.HOME_URL
    implemented = True
    supported_actions = ("list_favorites",)
    api_operations = (
        ApiOperation(
            op_id="cancel_favorites",
            name="批量取消收藏",
            description="完整扫描收藏夹，按【收藏于】时间批量删除（操作不可恢复）",
            danger=True,
            params=(
                ApiOperationParam(
                    key="media_id", label="收藏夹 ID", type="text",
                    placeholder="例如：290999545（默认收藏夹）",
                    help="可选；留空遍历全部收藏夹。收藏夹 URL 中 fid= 的数字",
                ),
                ApiOperationParam(
                    key="date_from", label="按收藏日期：从", type="date",
                    help="与「至」至少填一个；删除该日期（含）之后收藏的",
                ),
                ApiOperationParam(
                    key="date_to", label="按收藏日期：至", type="date",
                    help="闭区间（含当天）；例如删 2026 年之前填 2025-12-31",
                ),
                ApiOperationParam(
                    key="max_delete", label="最多删除条数", type="number",
                    placeholder="默认 0（全部命中）",
                    help="小批量验证用；如先删 2 条确认效果",
                ),
            ),
        ),
    )

    async def execute_api_operation(
        self, op_id: str, account: AccountContext, params: dict, on_event=None
    ) -> dict:
        if op_id == "cancel_favorites":
            return await self._op_cancel_favorites(account, params, on_event)
        raise ValueError(f"未知操作：{op_id}")

    async def _op_cancel_favorites(self, account: AccountContext, params: dict, on_event=None) -> dict:
        """批量取消收藏：按【收藏于】日期窗口过滤后 batch-del，必须至少给一个日期边界。"""
        dt_from, dt_to = parse_date_window(params)
        if not (dt_from or dt_to):
            raise ValueError("请至少填写一个日期边界（防止误删全部收藏）：例如删 2026 年之前填 date_to=2025-12-31")
        media_id = str((params or {}).get("media_id") or "").strip()
        if media_id and not media_id.isdigit():
            raise ValueError("media_id 需为收藏夹数字 ID（收藏夹 URL 中 fid= 的数字）")
        raw_max = str((params or {}).get("max_delete") or "").strip()
        max_delete = min(max(int(raw_max), 0), 10000) if raw_max.isdigit() else 0

        async def _progress(info: dict):
            if on_event:
                await on_event(info)

        logger.info("[%s] API 操作 cancel_favorites：media_id=%s 区间=%s~%s max_delete=%d",
                    account.account_id, media_id or "全部收藏夹", dt_from, dt_to, max_delete)
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        result = await api_client.cancel_fav_by_window(
            cookie_header, dt_from, dt_to, media_id=media_id,
            on_progress=_progress, max_delete=max_delete,
        )
        result["canceled"] = result["deleted"]
        if result["canceled"] == 0:
            result["note"] = "该日期区间内没有匹配的收藏，未执行删除"
        logger.info("[%s] 批量取消收藏完成：%s", account.account_id, result)
        return result

    async def edit_folder(self, account: AccountContext, params: dict) -> list[dict]:
        """编辑收藏夹（标题/简介/隐私）；cover 回填当前值避免被清空。

        成功后同步 extra.bilibili.folders 并返回新列表（FolderPicker dots 菜单调）。
        """
        media_id = str((params or {}).get("media_id") or "").strip()
        title = str((params or {}).get("title") or "").strip()
        intro = str((params or {}).get("intro") or "").strip()
        privacy = int((params or {}).get("privacy") or 0)
        if not (media_id and media_id.isdigit()):
            raise ValueError("media_id 需为收藏夹数字 ID")
        if not title:
            raise ValueError("收藏夹标题不能为空")
        if privacy not in (0, 1):
            raise ValueError("privacy 仅支持 0（公开）/ 1（私密）")

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        current = await self._current_folder(cookie_header, media_id)
        if current is None:
            raise ValueError(f"收藏夹不存在（可能已删除）：{media_id}")
        await asyncio.to_thread(
            api_client.folder_edit, cookie_header, media_id, title,
            intro or str(current.get("intro") or ""), privacy, str(current.get("cover") or ""),
        )
        logger.info("[%s] 编辑收藏夹 %s：%s", account.account_id, media_id, title)
        return await self._sync_folders_meta(account.account_id, cookie_header)

    async def delete_folder(self, account: AccountContext, media_id: str) -> list[dict]:
        """删除收藏夹（默认收藏夹不可删）；成功后同步 extra.bilibili.folders 并返回新列表。"""
        media_id = str(media_id or "").strip()
        if not (media_id and media_id.isdigit()):
            raise ValueError("media_id 需为收藏夹数字 ID")
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        current = await self._current_folder(cookie_header, media_id)
        if current is None:
            raise ValueError(f"收藏夹不存在（可能已删除）：{media_id}")
        if str(current.get("title") or "") == "默认收藏夹":
            raise ValueError("默认收藏夹不可删除")
        await asyncio.to_thread(api_client.folder_del, cookie_header, [media_id])
        logger.info("[%s] 删除收藏夹 %s：%s", account.account_id, media_id, current.get("title"))
        return await self._sync_folders_meta(account.account_id, cookie_header)

    async def _current_folder(self, cookie_header: str, media_id: str) -> dict | None:
        """从 list-all 找指定收藏夹的当前元数据（不存在返回 None）。"""
        up_mid = api_client._cookie_value(cookie_header, "DedeUserID")
        if not up_mid:
            raise LoginExpiredError("cookie 中无 DedeUserID，无法确定收藏夹归属")
        folders = await asyncio.to_thread(api_client.fetch_folder_list, cookie_header, up_mid)
        return next((f for f in folders if f["media_id"] == media_id), None)

    async def _sync_folders_meta(self, account_id: str, cookie_header: str) -> list[dict]:
        """收藏夹增删改后刷新 extra.bilibili.folders，保持前端列表与服务端一致。"""
        up_mid = api_client._cookie_value(cookie_header, "DedeUserID")
        folders = await asyncio.to_thread(api_client.fetch_folder_list, cookie_header, up_mid)
        from app.services import account_manager

        row = await account_manager.get_account(account_id)
        if row is not None:
            extra = row.get("extra") or {}
            bili = extra.get("bilibili") or {}
            bili["folders"] = folders
            extra["bilibili"] = bili
            await account_manager.update_account(
                account_id, extra=json.dumps(extra, ensure_ascii=False)
            )
        return folders

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

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：nav 接口取昵称/头像，list-all 取收藏夹列表。"""
        async with browser.session(account.profile_path, headless=True) as ctx:
            cookies = await ctx.cookies()
            mid = next(
                (c["value"] for c in cookies if c.get("name") == "DedeUserID" and c.get("value")),
                "",
            )
            if not mid:
                return
            data = await self._api_get(ctx, constants.NAV_API, {}, {})
            owner = {
                "mid": str(data.get("mid") or mid),
                "name": data.get("uname"),
                "face": data.get("face"),
            }
            headers = {"Referer": f"https://space.bilibili.com/{owner['mid']}/favlist"}
            folders_data = await self._api_get(
                ctx, constants.FAV_FOLDER_LIST_API, {"up_mid": owner["mid"]}, headers
            )
            folders = parse_folder_list(folders_data)["folders"]
            await self._save_owner(account.account_id, {"owner": owner, "folders": folders})
            logger.info(
                "[%s] 身份信息已回填：%s(%s)，%d 个收藏夹",
                account.account_id, owner.get("name"), owner["mid"], len(folders),
            )

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
