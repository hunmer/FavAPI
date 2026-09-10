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
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class FavoriteItem(BaseModel):
    content_id: str
    platform: str
    title: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    duration: int | None = None
    statistics: dict[str, Any] = Field(default_factory=dict)
    collected_at: str | None = None
    fetched_at: str | None = None
    url: str | None = None
