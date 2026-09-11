"""定时同步计划（schedules）的持久化与 cron 解析。"""
import json
import logging
from datetime import datetime

from croniter import croniter

from app.database import db
from app.services import account_manager
from app.utils import new_id, now_iso

logger = logging.getLogger("favapi.schedule")


def next_run_after(cron_expr: str) -> str:
    """基于当前时间计算 cron 下一次执行时间（本地时区、秒精度，与 now_iso 同格式）。"""
    return croniter(cron_expr, datetime.now().astimezone()).get_next(datetime).astimezone().isoformat(timespec="seconds")


def validate_cron(cron_expr: str):
    if not croniter.is_valid(cron_expr):
        raise ValueError(f"无效的 Cron 表达式：{cron_expr}（标准 5 段式，如 0 18 * * *）")


def _row_out(row: dict) -> dict:
    out = dict(row)
    try:
        out["params"] = json.loads(out.get("params") or "{}")
    except (TypeError, json.JSONDecodeError):
        out["params"] = {}
    return out


async def create_schedule(account_id: str, cron_expr: str, title: str = "",
                          action: str = "list_favorites", params: dict | None = None,
                          status: str = "active") -> dict:
    validate_cron(cron_expr)
    account = await account_manager.get_account(account_id)
    if account is None:
        raise ValueError(f"账号不存在：{account_id}")
    if status not in ("active", "paused"):
        raise ValueError("status 仅支持 active / paused")

    row = {
        "schedule_id": new_id("sched"),
        "title": title or f"{account['name']} 定时抓取",
        "account_id": account_id,
        "platform": account["platform"],
        "action": action,
        "params": json.dumps(params or {}, ensure_ascii=False),
        "cron_expr": cron_expr,
        "status": status,
        "last_run_at": None,
        "next_run_at": next_run_after(cron_expr) if status == "active" else None,
        "last_task_id": None,
        "created_at": now_iso(),
    }
    await db.execute(
        """INSERT INTO schedules (schedule_id, title, account_id, platform, action,
               params, cron_expr, status, last_run_at, next_run_at, last_task_id, created_at)
           VALUES (:schedule_id, :title, :account_id, :platform, :action,
                   :params, :cron_expr, :status, :last_run_at, :next_run_at, :last_task_id, :created_at)""",
        row,
    )
    return _row_out(row)


async def list_schedules() -> list[dict]:
    rows = await db.query_all("SELECT * FROM schedules ORDER BY created_at ASC")
    return [_row_out(r) for r in rows]


async def get_schedule(schedule_id: str) -> dict | None:
    row = await db.query_one("SELECT * FROM schedules WHERE schedule_id = ?", (schedule_id,))
    return _row_out(row) if row else None


async def update_schedule(schedule_id: str, **fields) -> dict | None:
    """更新指定列；cron 变更或恢复启用时重算 next_run_at（显式传入的 next_run_at 优先）。"""
    row = await get_schedule(schedule_id)
    if row is None:
        return None
    if "cron_expr" in fields:
        validate_cron(fields["cron_expr"])
    values = {k: v for k, v in fields.items()
              if k in ("title", "cron_expr", "status", "next_run_at")}
    if "params" in fields and fields["params"] is not None:
        values["params"] = json.dumps(fields["params"], ensure_ascii=False)

    if "next_run_at" not in values and (values.get("status") == "active" or "cron_expr" in values):
        # 恢复启用或修改周期：从当前时间重算下一次执行
        cron = values.get("cron_expr", row["cron_expr"])
        values["next_run_at"] = next_run_after(cron) if values.get("status", row["status"]) == "active" else None

    if values:
        cols = ", ".join(f"{k} = ?" for k in values)
        await db.execute(f"UPDATE schedules SET {cols} WHERE schedule_id = ?",
                         (*values.values(), schedule_id))
    return await get_schedule(schedule_id)


async def delete_schedule(schedule_id: str) -> bool:
    cur = await db.execute("DELETE FROM schedules WHERE schedule_id = ?", (schedule_id,))
    return cur.rowcount > 0


async def due_schedules(now: str) -> list[dict]:
    """到期（next_run_at <= now）且处于 active 状态的计划。"""
    rows = await db.query_all(
        "SELECT * FROM schedules WHERE status = 'active' AND next_run_at IS NOT NULL AND next_run_at <= ?",
        (now,),
    )
    return [_row_out(r) for r in rows]
