"""抓取执行 API（PRD 3.2）。"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models import FetchRequest
from app.services.task_executor import FetchValidationError, start_fetch

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
