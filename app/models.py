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
    new_favorites: int | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


# ---------- 定时任务 ----------

class ScheduleCreate(BaseModel):
    account_id: str
    cron_expr: str
    title: str = ""
    action: str = "list_favorites"
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
    collected_at: str | None = None
    fetched_at: str | None = None
    url: str | None = None
