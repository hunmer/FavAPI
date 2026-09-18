"""快手适配器：声明式浏览器抓取 + API 直连（__NS_hxfalcon 离线签名）。

浏览器模式（登录 / 滚动拦截）完全复用 DeclarativeAdapter（platforms/kuaishou/
platform.json）；本类在其上叠加 API 直连能力：fetch_favorites 按
params.method 分发，并提供 get_profile / list_favorites / list_likes
三个 API 操作。
"""
import asyncio
import json
import logging
import re
from pathlib import Path

from app.platforms.base import (
    AccountContext,
    ApiOperation,
    ApiOperationParam,
    FetchResult,
)
from app.platforms.declarative import DeclarativeAdapter
from app.utils import filter_by_date_window, parse_date_window
from . import api_client
from . import constants

logger = logging.getLogger("favapi.kuaishou")

# 单视频写操作（点赞/收藏）共用表单参数
_PHOTO_ACTION_PARAMS = (
    ApiOperationParam(
        key="photo_id", label="视频 ID", type="text", required=True,
        placeholder="例如：3xp76sm9jikcx7i",
        help="视频 photoId，可在视频分享链接或已抓取记录中获取",
    ),
    ApiOperationParam(
        key="user_id", label="作者 ID（可选）", type="text",
        help="作者 eid，服务端不校验，可留空",
    ),
)

# 批量写操作共用表单参数（ID 列表 / 日期区间二选一，日期优先）
_MULTI_ACTION_PARAMS = (
    ApiOperationParam(
        key="photo_ids", label="视频 ID 列表", type="textarea",
        placeholder="ID 之间用逗号或换行分隔，例如：\n3xp76sm9jikcx7i\n3xvmfg43gz5hpt9",
        help="与日期区间二选一；填写日期区间时忽略本项。点赞类操作会从已抓取记录自动补全作者 ID",
    ),
    ApiOperationParam(
        key="date_from", label="按日期区间：从", type="date",
        help="填日期区间时会完整扫描列表后按视频时间匹配，无需手填 ID",
    ),
    ApiOperationParam(
        key="date_to", label="按日期区间：至", type="date",
        help="闭区间（含当天）",
    ),
)


class KuaishouAdapter(DeclarativeAdapter):
    api_fetch_implemented = True  # 收藏列表支持 API 直连（params.method="api"）
    download_api_implemented = True  # 支持按 photo_id 解析下载直链（平台下载 → aria2c）
    api_operations = (
        ApiOperation(
            op_id="get_profile",
            name="获取用户信息",
            description="API 直连获取当前登录用户信息（昵称/粉丝数/关注数等，只读）",
        ),
        ApiOperation(
            op_id="list_favorites",
            name="获取收藏列表",
            description="API 直连拉取当前账号收藏列表（只读，不入库）",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认全部",
                    help="返回条数上限",
                ),
            ),
        ),
        ApiOperation(
            op_id="list_likes",
            name="获取点赞列表",
            description="API 直连拉取当前账号点赞列表（只读，不入库）",
            params=(
                ApiOperationParam(
                    key="count", label="数量 (0 为全部)", type="number",
                    placeholder="默认全部",
                    help="返回条数上限",
                ),
            ),
        ),
        ApiOperation(
            op_id="like_item",
            name="点赞视频",
            description="给指定视频点赞（幂等，重复执行保持已点赞）",
            params=_PHOTO_ACTION_PARAMS,
        ),
        ApiOperation(
            op_id="cancel_like_item",
            name="取消点赞",
            description="取消指定视频的点赞（操作不可恢复，需重新点赞）",
            danger=True,
            params=_PHOTO_ACTION_PARAMS,
        ),
        ApiOperation(
            op_id="collect_item",
            name="收藏视频",
            description="收藏指定视频（幂等，重复执行保持已收藏）",
            params=_PHOTO_ACTION_PARAMS,
        ),
        ApiOperation(
            op_id="cancel_collect_item",
            name="取消收藏",
            description="取消收藏指定视频（操作不可恢复，需重新收藏）",
            danger=True,
            params=_PHOTO_ACTION_PARAMS,
        ),
        ApiOperation(
            op_id="like_multi",
            name="批量点赞",
            description="按 ID 列表批量点赞视频（作者 ID 自动从已抓取记录补全）；当日次数用完自动停止",
            params=(
                ApiOperationParam(
                    key="photo_ids", label="视频 ID 列表", type="textarea", required=True,
                    placeholder="ID 之间用逗号或换行分隔，例如：\n3xp76sm9jikcx7i\n3xvmfg43gz5hpt9",
                    help="逐条执行，间隔 0.5s 防风控；未入库的视频需先抓取或改用单条点赞",
                ),
            ),
        ),
        ApiOperation(
            op_id="cancel_like_multi",
            name="批量取消点赞",
            description="批量取消点赞：ID 列表与日期区间二选一（日期优先，操作不可恢复）",
            danger=True,
            params=_MULTI_ACTION_PARAMS,
        ),
        ApiOperation(
            op_id="cancel_collect_multi",
            name="批量取消收藏",
            description="批量取消收藏：ID 列表与日期区间二选一（日期优先，操作不可恢复）",
            danger=True,
            params=_MULTI_ACTION_PARAMS,
        ),
        ApiOperation(
            op_id="resolve_download_urls",
            name="解析下载直链",
            description="按视频 ID 调详情接口返回可下载直链列表（只读，供平台下载/aria2c 使用）",
            params=(
                ApiOperationParam(
                    key="photo_id", label="视频 ID", type="text", required=True,
                    placeholder="例如：3xp76sm9jikcx7i",
                    help="视频 photoId，可在视频分享链接或已抓取记录中获取",
                ),
            ),
        ),
    )

    def __init__(self, base_dir: Path):
        spec = json.loads((Path(base_dir) / "platform.json").read_text(encoding="utf-8"))
        super().__init__(spec, base_dir=Path(base_dir))

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填主人信息：profile/get 直读（昵称/头像，纯 HTTP 无需浏览器）。"""
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        profile = await asyncio.to_thread(api_client.fetch_profile, cookie_header)
        owner = {
            "eid": str(profile.get("eid") or ""),
            "user_id": str(profile.get("user_id") or ""),
            "nickname": profile.get("user_name"),
            "avatar": profile.get("avatar"),
        }
        from app.services import account_manager  # 延迟导入避免循环依赖

        saved = await account_manager.save_owner(account.account_id, constants.PLATFORM, {"owner": owner})
        if saved is not None:
            logger.info("[%s] 身份信息已回填：%s(%s)",
                        account.account_id, owner.get("nickname"), owner["eid"])

    async def resolve_download_urls(self, account: AccountContext, content_id: str) -> list[dict]:
        """按 photo_id 调详情接口返回可下载直链列表（首项为推荐画质）。

        每个链接附 headers（UA / Referer）：快手 CDN 直链实测仅 UA 即可下载，
        Referer 与页面请求一致更稳，交给 aria2c 时作为请求头注入。
        """
        photo_id = str(content_id or "").strip()
        if not photo_id:
            raise ValueError("kuaishou 下载解析需要视频 photoId")
        headers = {
            "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
            "referer": f"https://www.kuaishou.com/short-video/{photo_id}",
        }
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        logger.info("[%s] 解析下载直链：photo_id=%s", account.account_id, photo_id)
        result = await asyncio.to_thread(api_client.fetch_photo_detail, cookie_header, photo_id)
        for link in result["links"]:
            if link.get("url"):
                link["headers"] = headers
            # 作者信息随链接下发：下载分类模板 {authorName}/{authorId} 变量来源
            link.setdefault("author_name", result.get("author_name"))
            link.setdefault("author_id", result.get("author_id"))
        return result["links"]

    async def fetch_favorites(self, account: AccountContext, params: dict,
                              on_batch=None) -> FetchResult:
        # 浏览器模拟模式已移除，仅保留 API 直连；method 入口保留供未来平台分发
        self.resolve_fetch_method(params)
        return await self.fetch_favorites_api(account, params, on_batch)

    async def fetch_favorites_api(self, account: AccountContext, params: dict,
                                  on_batch=None) -> FetchResult:
        """API 直连：profile cookies + __NS_hxfalcon 签名 + curl_cffi 直连 collect/list。

        cursor 语义与浏览器模式一致（已抓取条数偏移）；接口翻页内部用 pcursor。
        """
        raw_count = params.get("count")
        if raw_count in (None, ""):
            count = constants.DEFAULT_COUNT
        else:
            count = max(0, min(int(raw_count), constants.MAX_COUNT))  # 0 = 全部
        skip = max(0, int(params.get("cursor") or 0))
        logger.info("[%s] API 直连抓取收藏：count=%s cursor=%d",
                    account.account_id, count or "全部", skip)

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        user_eid = await asyncio.to_thread(api_client.resolve_user_eid, cookie_header)
        collected, last_has_more = await api_client.fetch_collect(
            cookie_header, user_eid, count=(count + skip) if count else 0,
            on_batch=on_batch,
        )
        window = collected[skip:] if not count else collected[skip: skip + count]
        logger.info("[%s] API 直连抓取完成：共 %d 条，返回 [%d:%d] %d 条",
                    account.account_id, len(collected), skip, skip + len(window),
                    len(window))
        return FetchResult(
            items=window,
            cursor=skip + len(window),
            has_more=last_has_more and (not count or len(collected) >= skip + count),
            total=len(collected),
        )

    async def execute_api_operation(
        self, op_id: str, account: AccountContext, params: dict, on_event=None
    ) -> dict:
        if op_id == "get_profile":
            return await self._op_get_profile(account)
        if op_id == "list_favorites":
            async def _fetch_favorites(_cookie, _count, _on_batch):
                eid = await asyncio.to_thread(api_client.resolve_user_eid, _cookie)
                return await api_client.fetch_collect(_cookie, eid, _count, on_batch=_on_batch)
            return await self._op_list(account, params, on_event, _fetch_favorites, "收藏")
        if op_id == "list_likes":
            return await self._op_list(
                account, params, on_event,
                lambda c, n, cb: api_client.fetch_like(c, n, on_batch=cb), "点赞")
        if op_id in ("like_item", "cancel_like_item"):
            return await self._op_photo_action(
                account, params, api_client.set_like,
                enable=op_id == "like_item", label=op_id)
        if op_id in ("collect_item", "cancel_collect_item"):
            return await self._op_photo_action(
                account, params, api_client.set_collect,
                enable=op_id == "collect_item", label=op_id)
        if op_id == "like_multi":
            return await self._op_multi_action(
                account, params, on_event, action="like", label=op_id)
        if op_id == "cancel_like_multi":
            return await self._op_multi_action(
                account, params, on_event, action="cancel_like", label=op_id)
        if op_id == "cancel_collect_multi":
            return await self._op_multi_action(
                account, params, on_event, action="cancel_collect", label=op_id)
        if op_id == "resolve_download_urls":
            photo_id = str((params or {}).get("photo_id") or "").strip()
            if not photo_id:
                raise ValueError("请填写视频 ID（photo_id）")
            return await self.resolve_download_urls(account, photo_id)
        raise ValueError(f"未知操作：{op_id}")

    async def _op_photo_action(self, account: AccountContext, params: dict,
                               action, enable: bool, label: str) -> dict:
        """单视频写操作共用实现（点赞/取消点赞/收藏/取消收藏）。"""
        photo_id = str((params or {}).get("photo_id") or "").strip()
        if not photo_id:
            raise ValueError("请填写视频 ID（photo_id）")
        author_user_id = str((params or {}).get("user_id") or "").strip()
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        data = await asyncio.to_thread(action, cookie_header, photo_id, author_user_id, enable)
        logger.info("[%s] API 操作 %s：%s", account.account_id, label, photo_id)
        result = {"photo_id": photo_id, "action": label, "result": data.get("result")}
        if "liked_remain_count" in data:  # 点赞接口返回当日剩余次数
            result["liked_remain_count"] = data["liked_remain_count"]
        return result

    # 批量动作 → 单视频写函数（enable 语义在此绑定）
    _MULTI_ACTIONS = {
        "like": lambda c, p, a: api_client.set_like(c, p, a, like=True),
        "cancel_like": lambda c, p, a: api_client.set_like(c, p, a, like=False),
        "cancel_collect": lambda c, p, a: api_client.set_collect(c, p, a, collect=False),
    }

    async def _op_multi_action(self, account: AccountContext, params: dict,
                               on_event, action: str, label: str) -> dict:
        """批量写操作共用实现：ID 列表 / 日期区间二选一（日期优先）。

        日期区间模式：全量扫描列表后按视频时间（collected_at 为发布时间兜底）
        匹配再执行 —— 发布时间不随翻页递减，无法像抖音那样提前终止翻页。
        """
        raw = str((params or {}).get("photo_ids") or "")
        photo_ids = [t for t in re.split(r"[\s,，;；]+", raw) if t]
        dt_from, dt_to = parse_date_window(params or {})
        if not photo_ids and not (dt_from or dt_to):
            raise ValueError("请填写视频 ID 列表或日期区间（二选一）")

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        fn = self._MULTI_ACTIONS[action]
        result: dict = {"action": label, "matched": 0}

        if dt_from or dt_to:
            async def _scan_progress(batch: dict):
                if on_event:
                    await on_event({
                        "type": "stage", "stage": "scanning", "page": batch.get("page"),
                        "total_fetched": len(batch.get("items") or []),
                    })

            if action == "cancel_collect":
                user_eid = await asyncio.to_thread(api_client.resolve_user_eid, cookie_header)
                collected, _ = await api_client.fetch_collect(
                    cookie_header, user_eid, 0, on_batch=_scan_progress)
            else:
                collected, _ = await api_client.fetch_like(
                    cookie_header, 0, on_batch=_scan_progress)
            matched = filter_by_date_window(collected, dt_from, dt_to)
            items = [{"photo_id": it["content_id"], "author_id": it.get("author_id") or ""}
                     for it in matched]
            result["scanned"] = len(collected)
            result["matched"] = len(items)
            logger.info("[%s] %s 日期区间 %s~%s：扫描 %d 条，命中 %d 条",
                        account.account_id, label, dt_from, dt_to,
                        len(collected), len(items))
        else:
            items = [{"photo_id": p, "author_id": ""} for p in photo_ids]
            if action in ("like", "cancel_like"):
                # photo/like 强校验作者 user_id（缺失 → result=21），
                # 从已抓取入库的 contents 自动补全
                known = await self._resolve_author_ids(photo_ids)
                missing = []
                for it in items:
                    it["author_id"] = known.get(it["photo_id"]) or ""
                    if not it["author_id"]:
                        missing.append(it["photo_id"])
                if missing:
                    raise ValueError(
                        f"点赞接口必须提供作者 ID，以下视频未在已抓取记录中找到："
                        f"{'、'.join(missing[:10])}（先抓取收藏/点赞列表入库，或改用单条操作并手填作者 ID）")
            result["matched"] = len(items)

        if not items:
            result["done"] = 0
            result["note"] = "没有匹配的视频，未执行操作"
            return result

        async def _exec_progress(info: dict):
            if on_event:
                await on_event({"type": "progress", **info})

        result.update(await api_client.execute_item_actions(
            cookie_header, items, fn, on_progress=_exec_progress, label=label,
            stop_on_quota=(action == "like")))
        logger.info("[%s] %s 完成：%s", account.account_id, label, result)
        return result

    @staticmethod
    async def _resolve_author_ids(photo_ids: list[str]) -> dict[str, str]:
        """从已入库的 contents 查视频 → 作者 eid 映射。"""
        from app.database import db

        placeholders = ",".join("?" for _ in photo_ids)
        rows = await db.query_all(
            f"SELECT content_id, author_id FROM contents "
            f"WHERE platform = ? AND content_id IN ({placeholders}) AND author_id IS NOT NULL",
            (constants.PLATFORM, *photo_ids),
        )
        return {r["content_id"]: r["author_id"] for r in rows}

    async def _op_get_profile(self, account: AccountContext) -> dict:
        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        profile = await asyncio.to_thread(api_client.fetch_profile, cookie_header)
        logger.info("[%s] API 操作 get_profile：%s(%s)",
                    account.account_id, profile.get("user_name"), profile.get("eid"))
        return profile

    async def _op_list(self, account: AccountContext, params: dict, on_event,
                       fetcher, label: str) -> dict:
        """只读列表操作共用实现（收藏 / 点赞）：count 限制 + 摘要输出。

        fetcher(cookie_header, count, on_batch) → (items, has_more)。
        """
        raw_count = str((params or {}).get("count") or "").strip()
        count = (min(max(int(raw_count), 0), constants.MAX_COUNT)
                 if raw_count.isdigit() else constants.DEFAULT_COUNT)
        logger.info("[%s] API 操作拉取%s列表：count=%s",
                    account.account_id, label, count or "全部")

        async def _collect_progress(batch: dict):
            if on_event:
                await on_event({
                    "type": "stage", "stage": "collecting",
                    "page": batch.get("page"), "total_fetched": len(batch.get("items") or []),
                })

        cookie_header = await api_client.profile_cookie_header(account.profile_path)
        collected, has_more = await fetcher(cookie_header, count, _collect_progress)
        summaries = [
            {
                "content_id": it.get("content_id"),
                "title": it.get("title"),
                "author_name": it.get("author_name"),
                "collected_at": it.get("collected_at"),
            }
            for it in collected[:100]
        ]
        return {
            "total": len(collected),
            "has_more": has_more,
            "items": summaries,
            "note": "仅展示前 100 条摘要" if len(collected) > 100 else "",
        }
