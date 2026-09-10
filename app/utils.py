"""通用小工具。"""
import uuid
from datetime import datetime


def now_iso() -> str:
    """本地时区、秒精度的 ISO 时间字符串，用于 SQLite TEXT 时间列。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    """生成短 ID，如 acc_a1b2c3d4 / task_9f8e7d6c。"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"
