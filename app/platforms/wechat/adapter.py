"""微信收藏 JSON 文件导入适配器。"""
import asyncio
import json
from pathlib import Path

from app.platforms.base import (
    AccountContext,
    ApiOperationParam,
    BasePlatformAdapter,
    FetchResult,
    FetchTarget,
    PARAM_COUNT,
    PARAM_CURSOR,
)
from app.platforms.wechat.parser import parse_export


class WeChatAdapter(BasePlatformAdapter):
    platform = "wechat"
    display_name = "微信收藏"
    home_url = "https://weixin.qq.com/"
    supported_actions = ("list_favorites",)
    fetch_targets = (
        FetchTarget(
            action="list_favorites", name="导入微信收藏",
            description="解析 WeChatDataAnalysis 导出的 messages.json 并入库",
            params=[
                ApiOperationParam(
                    key="json_path", label="微信收藏 JSON 文件路径", type="text",
                    required=True,
                    placeholder="conversations/.../messages.json",
                    help="请先用 WeChatDataAnalysis 导出；支持弹窗内直接上传 JSON 文件",
                ),
                PARAM_COUNT, PARAM_CURSOR,
            ],
        ),
    )

    async def login(self, account: AccountContext, timeout=None) -> bool:
        return True

    async def check_login_status(self, account: AccountContext) -> bool:
        return True

    def validate_params(self, params: dict) -> None:
        path = str((params or {}).get("json_path") or "").strip()
        if not path:
            raise ValueError("微信收藏导入需要提供 json_path（WeChatDataAnalysis 导出的 messages.json 路径）")
        p = Path(path).expanduser()
        if not p.is_file():
            raise ValueError(f"JSON 文件不存在：{path}")
        if p.suffix.lower() != ".json":
            raise ValueError("json_path 必须指向 .json 文件")

    async def fetch_favorites(self, account: AccountContext, params: dict, on_batch=None) -> FetchResult:
        self.validate_params(params)
        path = Path(str(params["json_path"])).expanduser()
        data = await asyncio.to_thread(lambda: json.loads(path.read_text(encoding="utf-8-sig")))
        items = parse_export(data)
        offset = max(0, int(params.get("cursor") or 0))
        count = int(params.get("count") or 0)
        selected = items[offset: offset + count if count > 0 else None]
        for item in selected:
            item.setdefault("platform", self.platform)
        if on_batch and selected:
            await on_batch({"page": offset, "items": selected, "total_fetched": offset + len(selected)})
        next_cursor = offset + len(selected)
        return FetchResult(items=selected, cursor=next_cursor if next_cursor < len(items) else None,
                           has_more=next_cursor < len(items), total=len(items),
                           meta={"source_file": str(path), "exported_at": data.get("exportedAt")})

