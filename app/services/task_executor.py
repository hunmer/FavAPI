"""抓取任务执行器：任务生命周期（pending → running → success / failed）+ 结果入库。"""
import asyncio
import logging

from app import config
from app.platforms import registry
from app.platforms.base import LoginExpiredError
from app.services import account_manager, data_store
from app.utils import new_id, now_iso

logger = logging.getLogger("favapi.task")

_MAX_ITEMS_IN_RESPONSE = 100  # 响应内嵌 items 上限，防超大 payload


class FetchValidationError(ValueError):
    """请求参数 / 账号状态问题，API 层转为 400。"""


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "Executable doesn't exist" in msg or "playwright install" in msg:
        return "浏览器内核未安装：请先执行 `.venv/Scripts/python.exe -m playwright install chromium` 后重试"
    return msg


def _item_summaries(items: list[dict]) -> list[dict]:
    return [
        {
            "content_id": it["content_id"],
            "title": it.get("title"),
            "author_name": it.get("author_name"),
            "duration": it.get("duration"),
            "fav_title": it.get("fav_title") or None,
            "collected_at": it.get("collected_at"),
        }
        for it in items[:_MAX_ITEMS_IN_RESPONSE]
    ]


async def validate_fetch(
    platform: str, account_id: str, action: str, params: dict
) -> tuple[dict, object]:
    """抓取前置校验；不合法抛 FetchValidationError（API 层转 400）。返回 (account, adapter)。"""
    account = await account_manager.get_account(account_id)
    if account is None:
        raise FetchValidationError(f"账号不存在：{account_id}")
    if account["platform"] != platform:
        raise FetchValidationError(
            f"账号 {account_id} 属于 {account['platform']} 平台，与请求的 {platform} 不一致"
        )
    adapter = registry.get_adapter(platform)
    if adapter is None:
        raise FetchValidationError(f"未知平台：{platform}")
    if not adapter.implemented:
        raise FetchValidationError(f"{adapter.display_name} 抓取暂未实现，即将支持")
    if action not in adapter.supported_actions:
        raise FetchValidationError(
            f"不支持的操作：{action}（{adapter.display_name} 当前支持：{', '.join(adapter.supported_actions)}）"
        )
    try:
        adapter.validate_params(params or {})
    except ValueError as exc:
        raise FetchValidationError(str(exc))
    if account["status"] == "disabled":
        raise FetchValidationError(f"账号 {account_id} 已禁用，请先启用")
    return account, adapter


async def start_fetch(
    platform: str, account_id: str, action: str, params: dict, async_run: bool = False
) -> dict:
    """校验请求并执行；async_run=true 立即返回 pending 任务，否则等待完成返回结果。"""
    account, _adapter = await validate_fetch(platform, account_id, action, params)

    task_id = new_id("task")
    await data_store.create_task(task_id, account_id, platform, action, params)

    if async_run:
        asyncio.create_task(_guarded_run(task_id, account, action, params))
        return {"task_id": task_id, "status": "pending", "task_url": f"/api/v1/tasks/{task_id}"}

    try:
        return await asyncio.wait_for(
            _run_task(task_id, account, action, params), timeout=config.FETCH_TIMEOUT
        )
    except asyncio.TimeoutError:
        await data_store.update_task(
            task_id,
            status="failed",
            error_message=f"抓取超时（>{config.FETCH_TIMEOUT}s）",
            finished_at=now_iso(),
        )
        row = await data_store.get_task(task_id)
        return row


async def _guarded_run(task_id: str, account: dict, action: str, params: dict):
    """async_run 模式的兜底：任何异常只记日志，不打崩事件循环。"""
    try:
        await _run_task(task_id, account, action, params)
    except Exception:
        logger.exception("后台抓取任务 %s 异常", task_id)


async def _run_task(task_id: str, account: dict, action: str, params: dict) -> dict:
    account_id = account["account_id"]
    await data_store.update_task(task_id, status="running", started_at=now_iso())
    await account_manager.update_account(account_id, last_used_at=now_iso())

    adapter = registry.get_adapter(account["platform"])
    try:
        result = await adapter.fetch_favorites(account_manager.to_context(account), params or {})
        summary = await data_store.save_fetch_result(account, result.items)
        payload = {
            "task_id": task_id,
            "account_id": account_id,
            "platform": account["platform"],
            "action": action,
            "status": "success",
            "result_count": summary["result_count"],
            "new_favorites": summary["new_favorites"],
            "cursor": result.cursor,
            "has_more": result.has_more,
            "items": _item_summaries(result.items),
        }
        if result.meta:
            payload["meta"] = result.meta
        await data_store.update_task(
            task_id, status="success", result_count=summary["result_count"], finished_at=now_iso()
        )
        return payload
    except asyncio.CancelledError:
        raise
    except LoginExpiredError as exc:
        await account_manager.update_account(account_id, status="expired")
        return await _fail_task(task_id, account_id, account["platform"], action, str(exc))
    except Exception as exc:
        logger.exception("抓取任务 %s 失败", task_id)
        return await _fail_task(task_id, account_id, account["platform"], action, friendly_error(exc))


async def _fail_task(
    task_id: str, account_id: str, platform: str, action: str, message: str
) -> dict:
    await data_store.update_task(
        task_id, status="failed", error_message=message[:2000], finished_at=now_iso()
    )
    return {
        "task_id": task_id,
        "account_id": account_id,
        "platform": platform,
        "action": action,
        "status": "failed",
        "result_count": 0,
        "new_favorites": 0,
        "error_message": message[:2000],
        "items": [],
    }


async def stream_fetch_events(task_id: str, account: dict, adapter, action: str, params: dict):
    """SSE 流式抓取：adapter 每批回调 → 增量入库 + 队列推送；结束推 done/error。

    消费方（API 层）断开时 generator 被 close，worker 取消并把任务标记为失败。
    """
    account_id = account["account_id"]
    await data_store.update_task(task_id, status="running", started_at=now_iso())
    await account_manager.update_account(account_id, last_used_at=now_iso())

    queue: asyncio.Queue = asyncio.Queue()
    seen: set[str] = set()
    saved_count = 0
    new_count = 0

    async def on_batch(batch: dict):
        nonlocal saved_count, new_count
        fresh = [it for it in batch.get("items") or [] if it.get("content_id") not in seen]
        if not fresh:
            return
        seen.update(it["content_id"] for it in fresh)
        summary = await data_store.save_fetch_result(account, fresh)
        saved_count += summary["result_count"]
        new_count += summary["new_favorites"]
        await queue.put({
            "type": "items",
            "folder": batch.get("folder"),
            "page": batch.get("page"),
            "new_count": len(fresh),
            "total_fetched": batch.get("total_fetched") or len(seen),
            "items": _item_summaries(fresh),
        })

    async def _worker():
        try:
            result = await adapter.fetch_favorites(
                account_manager.to_context(account), params or {}, on_batch=on_batch
            )
            payload = {
                "type": "done",
                "result_count": saved_count,
                "new_favorites": new_count,
                "cursor": result.cursor,
                "has_more": result.has_more,
                "total": result.total,
            }
            if result.meta:
                payload["meta"] = result.meta
            await data_store.update_task(
                task_id, status="success", result_count=saved_count, finished_at=now_iso()
            )
            await queue.put(payload)
        except asyncio.CancelledError:
            raise
        except LoginExpiredError as exc:
            await _stream_fail(task_id, account_id, queue, str(exc), expired=True)
        except Exception as exc:
            logger.exception("流式抓取任务 %s 失败", task_id)
            await _stream_fail(task_id, account_id, queue, friendly_error(exc))

    runner = asyncio.create_task(_worker())
    try:
        while True:
            msg = await queue.get()
            yield msg
            if msg["type"] in ("done", "error"):
                break
    finally:
        if not runner.done():
            runner.cancel()
            try:
                await runner
            except (asyncio.CancelledError, Exception):
                pass
            await data_store.update_task(
                task_id,
                status="failed",
                error_message="客户端断开，流式抓取中止",
                finished_at=now_iso(),
            )


async def _stream_fail(
    task_id: str, account_id: str, queue: asyncio.Queue, message: str, expired: bool = False
):
    if expired:
        await account_manager.update_account(account_id, status="expired")
    await data_store.update_task(
        task_id, status="failed", error_message=message[:2000], finished_at=now_iso()
    )
    await queue.put({"type": "error", "error_message": message[:2000]})
