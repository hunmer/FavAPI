"""AI 智能打标执行 API：SSE 流式（逐批推送进度）+ 智能创建标签建议。"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.models import FetchRequest
from app.services.ai_tagging import (
    TaggingValidationError,
    stream_tagging_events,
    suggest_groups,
    validate_tagging,
)

router = APIRouter(prefix="/api/v1/ai/tag", tags=["ai-tagging"])


@router.post("/stream")
async def tag_stream(req: FetchRequest):
    """一次性流式打标：event 格式 data: {"type": "task" | "item" | "done" | "error", ...}。

    item 事件逐条携带打标结果（title + tags），done/error 后流结束；
    客户端中途断开时任务标记失败，已入库条目保留。
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


class TagSuggestRequest(BaseModel):
    agent_id: str
    keyword: str


@router.post("/suggest")
async def tag_suggest(req: TagSuggestRequest):
    """智能创建标签：关键词 → AI 联想分组+标签建议（仅 OpenAI 兼容 Agent）。"""
    keyword = (req.keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="关键词不能为空")
    try:
        agent = await validate_tagging({"agent_id": req.agent_id})
    except TaggingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    from app.services import tag_store

    try:
        suggestions = await suggest_groups(agent, keyword, await tag_store.list_groups())
    except TaggingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{str(exc)[:300]}")
    return {"keyword": keyword, "groups": suggestions}
