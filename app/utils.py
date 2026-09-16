"""通用小工具。"""
import uuid
from datetime import datetime, time as dtime


def now_iso() -> str:
    """本地时区、秒精度的 ISO 时间字符串，用于 SQLite TEXT 时间列。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    """生成短 ID，如 acc_a1b2c3d4 / task_9f8e7d6c。"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ---------- 收藏日期区间（抓取过滤 / API 操作共用） ----------

def parse_date_window(params: dict) -> tuple[datetime | None, datetime | None]:
    """解析 params.date_from / date_to（YYYY-MM-DD）为本地时区边界（闭区间，含起止当天）。

    格式或顺序不合法抛 ValueError（调用方转 400）；两者都缺省返回 (None, None)。
    """
    raw_from = str((params or {}).get("date_from") or "").strip()
    raw_to = str((params or {}).get("date_to") or "").strip()
    if not raw_from and not raw_to:
        return None, None

    def _parse(value: str, name: str) -> datetime:
        try:
            dt = datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"{name} 格式无效：{value}（应为 YYYY-MM-DD）")
        # 年份合理性：拦下 date 输入框误解析出的 0026 / 2601 之类荒谬年份
        if not (2000 <= dt.year <= 2100):
            raise ValueError(f"{name} 年份超出合理范围（2000-2100）：{value}")
        return dt

    dt_from = _parse(raw_from, "date_from") if raw_from else None
    dt_to = _parse(raw_to, "date_to") if raw_to else None
    if dt_from and dt_to and dt_from > dt_to:
        raise ValueError("date_from 不能晚于 date_to")
    # 闭区间：from 取当天 00:00、to 取当天 23:59:59.999999，均转本地 aware 与 collected_at 对齐
    if dt_from:
        dt_from = datetime.combine(dt_from, dtime.min).astimezone()
    if dt_to:
        dt_to = datetime.combine(dt_to, dtime.max).astimezone()
    return dt_from, dt_to


def item_collected_time(item: dict) -> datetime | None:
    """collected_at（ISO）→ aware datetime；naive 视为本地时间，无效返回 None。"""
    raw = str(item.get("collected_at") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt.astimezone() if dt.tzinfo is None else dt


def filter_by_date_window(
    items: list[dict], dt_from: datetime | None, dt_to: datetime | None
) -> list[dict]:
    """按收藏时间过滤（collected_at 由各平台 parser 兜底为发布时间）；无法判定时间的条目丢弃。"""
    if not dt_from and not dt_to:
        return items
    kept = []
    for it in items:
        ts = item_collected_time(it)
        if ts is None:
            continue
        if dt_from and ts < dt_from:
            continue
        if dt_to and ts > dt_to:
            continue
        kept.append(it)
    return kept
