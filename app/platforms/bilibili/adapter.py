"""Bilibili 适配器：占位实现（PRD M4）。

仅注册平台元信息，所有动作抛 NotImplementedError，
由 API 层转换为友好的「暂未实现」提示，不影响抖音功能。
"""
from app.platforms.base import AccountContext, BasePlatformAdapter, FetchResult
from .constants import DISPLAY_NAME, NOT_IMPLEMENTED_MSG, PLATFORM


class BilibiliAdapter(BasePlatformAdapter):
    platform = PLATFORM
    display_name = DISPLAY_NAME
    implemented = False
    supported_actions = ("list_favorites",)  # 预留，与抖音 action 命名对齐

    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    async def check_login_status(self, account: AccountContext) -> bool:
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    async def fetch_favorites(self, account: AccountContext, params: dict) -> FetchResult:
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)
