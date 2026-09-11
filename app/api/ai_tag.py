"""AI 智能打标执行 API：SSE 流式（逐批推送进度）。"""
import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.models import FetchRequest
from app.services.ai_tagging import TaggingValidationError, stream_tagging_events, validate_tagging

router = APIRouter(prefix="/api/v1/ai/tag", tags=["ai-tagging"])


@router.post("/stream")
async def tag_stream(req: FetchRequest):
    """一次性流式打标：event 格式 data: {"type": "task" | "batch" | "done" | "error", ...}。

    batch 事件携带本批打标结果（title + tags），done/error 后流结束；
    客户端中途断开时任务标记失败，已入库批次保留。
    """
    try:
        agent = await validate_tagging(req.params)
    except TaggingValidationError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    async def sse():
        async for msg in stream_tagging_events(agent, req.platform, req.params):
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
