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


@dataclass
class ApiOperationParam:
    """API 操作表单的一个输入项（前端据此渲染弹窗表单）。"""
    key: str
    label: str
    type: str = "text"        # text | textarea | number | date | select
    required: bool = False
    placeholder: str = ""
    help: str = ""
    options: tuple[tuple[str, str], ...] = ()  # select 的选项：(value, 显示名)


@dataclass
class ApiOperation:
    """平台对外暴露的一个可执行 API 操作（写操作 / 管理类，与收藏抓取分离）。"""
    op_id: str
    name: str
    description: str = ""
    params: list[ApiOperationParam] = field(default_factory=list)
    danger: bool = False      # 前端弹二次确认


class BasePlatformAdapter(ABC):
    platform: str = ""
    display_name: str = ""
    home_url: str = ""             # 平台首页（手动浏览窗口的起始页）
    homepage: str = ""             # 手动浏览按钮打开的官网首页（可与抓取 URL 不同）
    icon: str = ""                 # 图标文件名（相对平台目录，供 /platforms/{id}/icon 下发）
    implemented: bool = True          # False = 占位平台
    supported_actions: tuple[str, ...] = ()
    # 收藏列表是否支持 API 直连抓取（params.method="api"）；
    # 支持的平台覆写为 True 并实现 fetch_favorites_api，在 fetch_favorites 开头分发
    api_fetch_implemented: bool = False
    # 平台对外暴露的可执行 API 操作（写操作/管理类）；元数据下发前端渲染卡片+表单
    api_operations: tuple[ApiOperation, ...] = ()

    @abstractmethod
    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        """有头浏览器登录（扫码），成功返回 True。"""

    @abstractmethod
    async def check_login_status(self, account: AccountContext) -> bool:
        """检查登录态是否有效。"""

    def validate_params(self, params: dict) -> None:
        """抓取前参数校验（可选覆写）；不合法抛 ValueError，由任务执行器转为 400。

        默认校验抓取方式 method 的合法性（未实现 API 直连的平台提前拒绝）。
        """
        self.resolve_fetch_method(params)

    @abstractmethod
    async def fetch_favorites(self, account: AccountContext, params: dict, on_batch=None) -> FetchResult:
        """抓取收藏列表，params 支持 count / cursor / method 等。

        on_batch 提供时（流式抓取）：每抓到一批 items 调用一次
        await on_batch({"folder": ..., "page": ..., "items": [...], "total_fetched": ...})，
        便于调用方增量入库 / SSE 推送；不提供时行为与原同步抓取一致。

        params.method = "api" 时走接口直连（需平台实现 fetch_favorites_api 且
        api_fetch_implemented = True），缺省 "browser" 浏览器模拟；分发见 resolve_fetch_method。
        """

    def resolve_fetch_method(self, params: dict) -> str:
        """解析收藏抓取执行方式（browser=浏览器模拟 / api=接口直连）。

        不合法或平台未实现 api 时抛 ValueError，由任务执行器转为 400；
        fetch_favorites 实现开头应调用本方法完成 method 分发。
        """
        method = str((params or {}).get("method") or "browser").lower()
        if method not in ("browser", "api"):
            raise ValueError(f"未知抓取方式 method={method}（可选 browser / api）")
        if method == "api" and not self.api_fetch_implemented:
            raise ValueError(f"{self.display_name} 暂不支持 API 请求方式，请使用浏览器模拟")
        return method

    async def fetch_favorites_api(self, account: AccountContext, params: dict, on_batch=None) -> FetchResult:
        """收藏列表 API 直连抓取（可选实现，签名与 fetch_favorites 一致）。

        默认未实现；支持的平台在 fetch_favorites 中按 resolve_fetch_method 分发到这里。
        """
        raise NotImplementedError(f"{self.display_name} 未实现 API 请求抓取方式")

    def get_api_operation(self, op_id: str) -> ApiOperation | None:
        for op in self.api_operations:
            if op.op_id == op_id:
                return op
        return None

    async def execute_api_operation(
        self, op_id: str, account: AccountContext, params: dict, on_event=None
    ) -> dict:
        """执行一个 API 操作（可选实现）；返回结果 dict 原样下发前端。

        默认未实现；支持的平台按 op_id 分发到具体操作，参数不合法抛 ValueError（API 层转 400）。
        on_event(evt: dict) 提供时（流式执行）：阶段性进度逐条回调
        （如 {"type": "stage"|"matched"|"progress", ...}），便于 SSE 推送。
        """
        raise NotImplementedError(f"{self.display_name} 未实现 API 操作：{op_id}")

    async def refresh_profile(self, account: AccountContext) -> None:
        """登录成功后回填账号身份信息（昵称/头像/收藏夹等，可选覆写）。

        实现方自行写入账号 extra；失败不抛出（调用方已兜底，仅影响展示）。
        """
