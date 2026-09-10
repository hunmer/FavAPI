"""Web 管理界面路由（Jinja2 页面，数据全部通过 /api/v1 JSON 接口获取）。"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["web"])

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/", include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"page": "accounts"})


@router.get("/accounts/{account_id}", include_in_schema=False)
async def account_detail(request: Request, account_id: str):
    return templates.TemplateResponse(
        request, "account_detail.html", {"page": "account_detail", "account_id": account_id}
    )


@router.get("/tasks", include_in_schema=False)
async def tasks_page(request: Request):
    return templates.TemplateResponse(request, "tasks.html", {"page": "tasks"})


@router.get("/favorites", include_in_schema=False)
async def favorites_page(request: Request):
    return templates.TemplateResponse(request, "favorites.html", {"page": "favorites"})
