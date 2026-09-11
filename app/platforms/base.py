"""平台适配器抽象基类与通用数据结构。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AccountContext:
    """适配器所需的账号上下文（服务层从 accounts 表构造）。"""
    account_id: str
    platform: str
    name: str
    profile_path: str


@dataclass
class FetchResult:
    """fetch_favorites 的统一返回。items 为解析后的通用 content 行（见 parser）。"""
    items: list[dict] = field(default_factory=list)
    cursor: int | None = None   # 下次增量抓取的偏移
    has_more: bool = False
    total: int = 0
    meta: dict = field(default_factory=dict)  # 平台附加信息（如 Bilibili 收藏夹主人）


class LoginExpiredError(Exception):
    """登录态失效：抓取中途检测到未登录时抛出，由任务执行器标记账号 expired。"""


class BasePlatformAdapter(ABC):
    platform: str = ""
    display_name: str = ""
    home_url: str = ""             # 平台首页（手动浏览窗口的起始页）
    implemented: bool = True          # False = 占位平台
    supported_actions: tuple[str, ...] = ()

    @abstractmethod
    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        """有头浏览器登录（扫码），成功返回 True。"""

    @abstractmethod
    async def check_login_status(self, account: AccountContext) -> bool:
        """检查登录态是否有效。"""

    def validate_params(self, params: dict) -> None:
        """抓取前参数校验（可选覆写）；不合法抛 ValueError，由任务执行器转为 400。"""

    @abstractmethod
    async def fetch_favorites(self, account: AccountContext, params: dict, on_batch=None) -> FetchResult:
        """抓取收藏列表，params 支持 count / cursor 等。

        on_batch 提供时（流式抓取）：每抓到一批 items 调用一次
        await on_batch({"folder": ..., "page": ..., "items": [...], "total_fetched": ...})，
        便于调用方增量入库 / SSE 推送；不提供时行为与原同步抓取一致。
        """

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填账号身份信息（昵称/头像/收藏夹等，可选覆写）。

        实现方自行写入账号 extra；失败不抛出（调用方已兜底，仅影响展示）。
        """
