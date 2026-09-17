"""快手适配器：声明式浏览器抓取 + API 直连（__NS_hxfalcon 离线签名）。

浏览器模式（登录 / 滚动拦截）完全复用 DeclarativeAdapter（platforms/kuaishou/
platform.json）；本类在其上叠加 API 直连能力：fetch_favorites 按
params.method 分发，并提供 get_profile / list_favorites / list_likes
三个 API 操作。
"""
import asyncio
import json
import logging
from pathlib import Path

from app.platforms.base import (
    AccountContext,
    ApiOperation,
    ApiOperationParam,
    FetchResult,
)
from app.platforms.declarative import DeclarativeAdapter
from app.utils import parse_date_window
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


class KuaishouAdapter(DeclarativeAdapter):
    api_fetch_implemented = True  # 收藏列表支持 API 直连（params.method="api"）
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
                    placeholder="默认 20",
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
                    placeholder="默认 20",
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
    )

    def __init__(self, base_dir: Path):
        spec = json.loads((Path(base_dir) / "platform.json").read_text(encoding="utf-8"))
        super().__init__(spec, base_dir=Path(base_dir))

    async def fetch_favorites(self, account: AccountContext, params: dict,
                              on_batch=None) -> FetchResult:
        if self.resolve_fetch_method(params) == "api":
            return await self.fetch_favorites_api(account, params, on_batch)
        return await super().fetch_favorites(account, params, on_batch)

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
