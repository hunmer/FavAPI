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


@dataclass
class FetchTarget:
    """一个可抓取入库的列表目标（收藏 / 喜欢 / 稍后再看…）。

    前端按此渲染卡片 + 弹窗表单，提交 action + params 走 /fetch 任务管线；
    source 为入库 favorites.source 的来源标记，空串 = 收藏列表。
    """
    action: str
    name: str
    description: str = ""
    source: str = ""
    params: list[ApiOperationParam] = field(default_factory=list)


# 抓取目标的通用参数（count / cursor / 收藏日期区间），各平台声明 target 时复用
PARAM_COUNT = ApiOperationParam(
    key="count", label="抓取数量 (0 为全部)", type="number", placeholder="默认全部",
    help="返回条数上限；留空或 0 抓取全部（结果以流式方式实时入库）",
)
PARAM_CURSOR = ApiOperationParam(
    key="cursor", label="起始游标 (已抓取条数)", type="number", placeholder="留空从第 1 条开始",
    help="用于翻页续抓，填上次抓取结果返回的 cursor",
)
PARAM_DATE_FROM = ApiOperationParam(
    key="date_from", label="收藏日期从", type="date",
    help="可选；平台无收藏时间时按发布时间判定",
)
PARAM_DATE_TO = ApiOperationParam(
    key="date_to", label="收藏日期至", type="date",
    help="可选，闭区间（含当天）",
)

# 未声明 fetch_targets 的平台使用默认收藏列表目标（仅通用参数）
DEFAULT_FETCH_TARGETS = (
    FetchTarget(
        action="list_favorites", name="抓取收藏列表",
        description="抓取当前账号收藏列表并入库",
        params=[PARAM_COUNT, PARAM_DATE_FROM, PARAM_DATE_TO],
    ),
)


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
    # 可抓取入库的列表目标（收藏/喜欢/稍后再看…）；空 = 默认仅收藏列表
    fetch_targets: tuple[FetchTarget, ...] = ()
    # 是否提供「平台下载」能力（按视频 ID 解析直链，配合 aria2c 下载）；
    # 支持的平台覆写为 True 并实现 resolve_download_urls
    download_api_implemented: bool = False
    # 是否支持特别关注（follows）体系（关注列表拉取 / 博主主页作品 / 作品播放 / 一键同步）；
    # 支持的平台覆写为 True 并实现下列 follows_* 方法，follows API 层按博主 platform 分发
    follows_api_implemented: bool = False

    @abstractmethod
    async def login(self, account: AccountContext, timeout: float | None = None) -> bool:
        """有头浏览器登录（扫码），成功返回 True。"""

    @abstractmethod
    async def check_login_status(self, account: AccountContext) -> bool:
        """检查登录态是否有效。"""

    async def check_login_status_and_refresh(self, account: AccountContext) -> tuple[bool, bool]:
        """登录态检查 + 有效时回填身份，返回 (logged_in, profile_refreshed)。

        默认组合实现（check_login_status + refresh_profile 各自执行）；
        身份刷新失败不影响检查结论（refreshed=False）。
        平台可覆写为单会话版本：一次读 cookie / 一次接口同时完成两件事
        （如 Threads 的 viewer 身份在登录校验时已随响应拿到）。
        """
        if not await self.check_login_status(account):
            return False, False
        refreshed = False
        try:
            await self.refresh_profile(account)
            refreshed = True
        except Exception:  # 身份刷新为附带能力，失败不影响登录态结论
            pass
        return True, refreshed

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

    def effective_fetch_targets(self) -> tuple[FetchTarget, ...]:
        """对外抓取目标（未声明时回落默认收藏列表目标）。"""
        return self.fetch_targets or DEFAULT_FETCH_TARGETS

    def get_fetch_target(self, action: str) -> FetchTarget | None:
        for t in self.effective_fetch_targets():
            if t.action == action:
                return t
        return None

    def fetch_source(self, action: str) -> str:
        """action 对应的入库来源标记（favorites.source；未声明目标时空 = 收藏列表）。"""
        target = self.get_fetch_target(action)
        return target.source if target else ""

    async def fetch_by_action(
        self, action: str, account: AccountContext, params: dict, on_batch=None
    ) -> FetchResult:
        """按 action 分发抓取（多列表目标平台覆写：如抖音的喜欢/稍后再看）。

        默认所有 action 走 fetch_favorites；action 合法性由调用方校验。
        """
        return await self.fetch_favorites(account, params, on_batch)

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

    async def resolve_download_urls(self, account: AccountContext, content_id: str) -> list[dict]:
        """按视频 ID 解析可下载直链列表（可选实现，供 aria2c 平台下载）。

        每项 {"url": 直链, "label": 描述, "ext": 扩展名, "size": 字节数, "kind": 类型,
              "width"/"height": 可选分辨率, "headers": 可选下载请求头}；
        kind 取 "video"（默认，走清晰度选链）/"image"（图文逐张全下）/"text"
        （无 url，text 字段为文案，调用方直接落盘 txt）。首个视频项视为推荐地址；
        未实现的平台抛 NotImplementedError。
        """
        raise NotImplementedError(f"{self.display_name} 未实现下载直链解析")

    # ---------- 特别关注（follows）体系能力（可选实现） ----------

    async def follows_profile_cookie(self, account: AccountContext) -> str:
        """取账号登录 cookie 头（follows 各接口共用；失效抛 LoginExpiredError）。"""
        raise NotImplementedError(f"{self.display_name} 未实现特别关注能力")

    def follows_self_uid(self, cookie_header: str) -> str:
        """从登录态提取当前账号的博主主键（douyin: sec_uid；bilibili: mid）。空串 = 提取失败。"""
        raise NotImplementedError(f"{self.display_name} 未实现特别关注能力")

    def follows_validate_uid(self, sec_uid: str) -> None:
        """校验博主主键格式（可选覆写）；不合法抛 ValueError，由 follows API 层转 400。"""

    async def follows_fetch_following(self, cookie_header: str, self_uid: str,
                                      count: int = 0, on_batch=None) -> tuple[list[dict], bool]:
        """拉取关注列表（count 0 = 全部）→ (followings, has_more)。

        条目统一精简结构 {sec_uid, uid, unique_id, nickname, signature,
        avatar_url, follower_count, aweme_count, is_top}（平台缺失字段置 None/空）。
        """
        raise NotImplementedError(f"{self.display_name} 未实现特别关注能力")

    async def follows_fetch_posts_page(self, cookie_header: str, sec_uid: str,
                                       cursor: int | str = 0, count: int = 18) -> dict:
        """拉取一页博主主页作品 → {items, cursor, has_more}。

        cursor 语义：0 = 首页，响应 cursor 供下次翻页，末页返回 0（无更多）；
        形态 int（时间戳/页码）或 str（xiaohongshu 不透明十六进制游标，超出
        JS 安全整数不可数值化，原样透传）；items 为通用 content 行（parser 输出，
        直接入库/展示）。
        """
        raise NotImplementedError(f"{self.display_name} 未实现特别关注能力")

    async def follows_play_info(self, cookie_header: str, content_id: str) -> dict:
        """作品播放信息 → PlayerModal 统一结构：
        {aweme_id, desc, create_time(epoch 秒), duration, statistics,
         author:{nickname, sec_uid}, video_urls, images, music_url}。
        """
        raise NotImplementedError(f"{self.display_name} 未实现特别关注能力")

    async def sync_author_posts(self, account: AccountContext, author_row: dict,
                                cookie_header: str, count: int) -> list[dict]:
        """拉取单博主最新 count 条作品（通用 content 行），并回填 last_synced_at / 身份字段。

        不负责入库：follows /sync 路由与 follow_sync 抓取目标（task 体系统一入库）共用本方法。
        """
        raise NotImplementedError(f"{self.display_name} 未实现特别关注能力")
