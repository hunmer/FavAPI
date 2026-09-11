"""定时调度器：后台循环扫描到期计划并触发抓取任务（async 后台执行）。"""
import asyncio
import logging

from app.services import data_store, schedule_store
from app.utils import now_iso

logger = logging.getLogger("favapi.scheduler")

CHECK_INTERVAL = 30  # 扫描间隔（秒）

_task: asyncio.Task | None = None


async def start():
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run_forever())
        logger.info("定时调度器已启动（每 %ss 扫描一次到期计划）", CHECK_INTERVAL)


async def stop():
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        logger.info("定时调度器已停止")


async def _run_forever():
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("调度循环异常")
        await asyncio.sleep(CHECK_INTERVAL)


async def tick():
    """扫描到期计划并逐个触发；供调度循环与测试调用。"""
    for row in await schedule_store.due_schedules(now_iso()):
        try:
            await trigger_schedule(row["schedule_id"])
        except ValueError as exc:
            # 账号禁用/被删等预期内校验失败：trigger_schedule 已推进 next_run_at，仅告警
            logger.warning("计划 %s 本轮跳过：%s", row.get("schedule_id"), exc)
        except Exception:
            logger.exception("触发计划 %s 失败", row.get("schedule_id"))


async def trigger_schedule(schedule_id: str) -> dict:
    """立即执行计划（手动触发与定时触发共用）；返回任务信息。

    防重入：上一次触发的任务仍在 pending / running 时跳过本次。
    """
    row = await schedule_store.get_schedule(schedule_id)
    if row is None:
        raise ValueError(f"计划不存在：{schedule_id}")

    if row.get("last_task_id"):
        last = await data_store.get_task(row["last_task_id"])
        if last and last.get("status") in ("pending", "running"):
            return {"schedule_id": schedule_id, "task_id": row["last_task_id"],
                    "status": last["status"], "skipped": "上一轮任务尚未结束"}

    from app.services.task_executor import start_fetch  # 延迟导入避免循环依赖

    try:
        result = await start_fetch(row["platform"], row["account_id"], row["action"],
                                   row.get("params") or {}, async_run=True)
    except Exception as exc:
        # 账号被删/禁用等校验失败：推进 next_run_at 避免每轮重复失败刷屏
        logger.warning("计划 %s 触发校验失败：%s", schedule_id, exc)
        await schedule_store.update_schedule(
            schedule_id, next_run_at=schedule_store.next_run_after(row["cron_expr"])
        )
        raise

    await schedule_store.update_schedule(
        schedule_id,
        last_run_at=now_iso(),
        last_task_id=result["task_id"],
        next_run_at=schedule_store.next_run_after(row["cron_expr"]),
    )
    logger.info("计划 %s 已触发任务 %s（下次 %s）", schedule_id, result["task_id"],
                (await schedule_store.get_schedule(schedule_id) or {}).get("next_run_at"))
    return {"schedule_id": schedule_id, **result}
