"""抓取执行 API（PRD 3.2）。"""
import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.models import FetchRequest
from app.services import data_store
from app.services.task_executor import (
    FetchValidationError,
    start_fetch,
    stream_fetch_events,
    validate_fetch,
)
from app.utils import new_id

router = APIRouter(prefix="/api/v1", tags=["fetch"])


@router.post("/fetch")
async def fetch(req: FetchRequest):
    """统一抓取入口。

    - 默认同步等待并返回结果（含 items 摘要与数量）
    - async_run=true 时立即返回 202 + task_id，后台执行，轮询 /api/v1/tasks/{task_id}
    """
    try:
        result = await start_fetch(
            req.platform, req.account_id, req.action, req.params, req.async_run
        )
    except FetchValidationError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    status_code = 202 if result.get("status") == "pending" else 200
    return JSONResponse(status_code=status_code, content=result)


@router.post("/fetch/stream")
async def fetch_stream(req: FetchRequest):
    """SSE 流式抓取：逐批推送增量，事件格式 data: {"type": ...}。

    type: task（任务 id）/ items（本批增量+进度）/ done（汇总）/ error（失败信息）。
    适用 count=0 全量等长耗时抓取，请求端实时消费。
    """
    try:
        account, adapter = await validate_fetch(
            req.platform, req.account_id, req.action, req.params
        )
    except FetchValidationError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    task_id = new_id("task")
    await data_store.create_task(task_id, req.account_id, req.platform, req.action, req.params)

    async def sse():
        yield f"data: {json.dumps({'type': 'task', 'task_id': task_id}, ensure_ascii=False)}\n\n"
        async for msg in stream_fetch_events(task_id, account, adapter, req.action, req.params):
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
