"""API 请求 / 响应模型（Pydantic）。"""
from typing import Any

from pydantic import BaseModel, Field


# ---------- 账号 ----------

class AccountCreate(BaseModel):
    platform: str
    name: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class AccountUpdate(BaseModel):
    """仅允许改名和启停；平台与 profile 创建后不可变。"""
    name: str | None = None
    status: str | None = None  # active / disabled


class AccountOut(BaseModel):
    account_id: str
    platform: str
    name: str
    status: str
    profile_path: str | None = None
    last_login_at: str | None = None
    last_used_at: str | None = None
    created_at: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    avatar: str | None = None  # extra.{platform}.owner.avatar 统一提取（本地化 URL）


# ---------- 抓取 ----------

class FetchRequest(BaseModel):
    platform: str
    account_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    async_run: bool = False  # true 时立即返回 task_id，后台执行 + 轮询


class FetchItemSummary(BaseModel):
    content_id: str
    title: str | None = None
    author_name: str | None = None
    duration: int | None = None
    collected_at: str | None = None


# ---------- 任务 / 数据查询 ----------

class TaskOut(BaseModel):
    task_id: str
    account_id: str | None = None
    platform: str | None = None
    action: str | None = None
    request_params: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    result_count: int | None = None
    new_favorites: int | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


# ---------- 定时任务 ----------

class ScheduleCreate(BaseModel):
    cron_expr: str
    account_id: str = ""   # ai_tag 不绑定账号，可为空
    title: str = ""
    action: str = "list_favorites"
    platform: str | None = None  # ai_tag 指定打标平台（空 = 全平台）
    params: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"


class ScheduleUpdate(BaseModel):
    title: str | None = None
    cron_expr: str | None = None
    params: dict[str, Any] | None = None
    status: str | None = None  # active / paused


class ScheduleOut(BaseModel):
    schedule_id: str
    title: str | None = None
    account_id: str
    platform: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    cron_expr: str
    status: str
    last_run_at: str | None = None
    next_run_at: str | None = None
    last_task_id: str | None = None
    created_at: str | None = None


class FavoriteItem(BaseModel):
    content_id: str
    account_id: str | None = None
    platform: str
    title: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    duration: int | None = None
    statistics: dict[str, Any] = Field(default_factory=dict)
    fav_media_id: str | None = None  # 归属收藏夹（Bilibili）
    fav_title: str | None = None
    source: str | None = None  # 入库来源（收藏列表 / 喜欢列表 / 稍后再看列表…；空 = 收藏列表）
    collected_at: str | None = None
    fetched_at: str | None = None
    url: str | None = None
    tags: list[str] = Field(default_factory=list)  # AI 智能打标结果
    tagged_at: str | None = None


# ---------- 下载队列 ----------

class DownloadCreate(BaseModel):
    content_id: str
    platform: str
    account_id: str = ""    # 来源账号（yt-dlp 下载时携带其登录 Cookies）
    title: str = ""
    url: str = ""           # 缺省时按平台模板用 content_id 生成
    downloader: str = "yt-dlp"  # yt-dlp / videodl


class DownloadOut(BaseModel):
    download_id: str
    platform: str | None = None
    content_id: str | None = None
    account_id: str | None = None
    title: str | None = None
    url: str
    downloader: str
    status: str
    progress: str | None = None
    output_path: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


# ---------- AI Agent 配置 ----------

class AgentCreate(BaseModel):
    name: str
    base_url: str  # OpenAI 兼容服务地址，如 https://api.openai.com/v1
    api_key: str
    model_id: str


class AgentUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_id: str | None = None


class AgentOut(BaseModel):
    agent_id: str
    name: str
    base_url: str
    api_key: str
    model_id: str
    created_at: str | None = None
