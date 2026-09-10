"""账号管理 API（PRD 3.1）。"""
import asyncio

from fastapi import APIRouter, HTTPException

from app.models import AccountCreate, AccountOut, AccountUpdate
from app.platforms import registry
from app.services import account_manager
from app.services.task_executor import friendly_error
from app.utils import now_iso

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])

platforms_router = APIRouter(prefix="/api/v1", tags=["accounts"])


@platforms_router.get("/platforms")
async def list_platforms():
    """全部平台元信息（含是否已实现、支持的 action）。"""
    return {"platforms": registry.platform_infos()}


async def _get_account_or_404(account_id: str) -> dict:
    account = await account_manager.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"账号不存在：{account_id}")
    return account


def _require_adapter(platform: str):
    adapter = registry.get_adapter(platform)
    if adapter is None:
        raise HTTPException(status_code=400, detail=f"未知平台：{platform}")
    if not adapter.implemented:
        raise HTTPException(status_code=400, detail=f"{adapter.display_name} 暂未实现，即将支持")
    return adapter


@router.get("", response_model_exclude_none=True)
async def list_accounts():
    accounts = await account_manager.list_accounts()
    for a in accounts:
        a["logging_in"] = account_manager.is_logging_in(a["account_id"])
    return {"accounts": [AccountOut(**a).model_dump() for a in accounts]}


@router.post("", status_code=201)
async def create_account(body: AccountCreate):
    try:
        row = await account_manager.create_account(body.platform, body.name, body.extra)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AccountOut(**row).model_dump()


@router.get("/{account_id}")
async def get_account(account_id: str):
    account = await _get_account_or_404(account_id)
    return AccountOut(**account).model_dump()


@router.patch("/{account_id}")
async def update_account(account_id: str, body: AccountUpdate):
    await _get_account_or_404(account_id)
    fields = body.model_dump(exclude_none=True)
    if fields.get("status") not in (None, "active", "disabled", "expired"):
        raise HTTPException(status_code=400, detail="status 仅支持 active / disabled / expired")
    row = await account_manager.update_account(account_id, **fields)
    return AccountOut(**row).model_dump()


@router.delete("/{account_id}")
async def delete_account(account_id: str):
    await _get_account_or_404(account_id)
    await account_manager.delete_account(account_id)
    return {"deleted": account_id}


@router.post("/{account_id}/login", status_code=202)
async def start_login(account_id: str):
    """打开有头浏览器等待扫码；立即返回，前端轮询 status 接口观察结果。"""
    account = await _get_account_or_404(account_id)
    adapter = _require_adapter(account["platform"])
    if account["status"] == "disabled":
        raise HTTPException(status_code=400, detail=f"账号 {account_id} 已禁用，请先启用")
    from app.services import browser

    await browser.close_manual(account_id)  # 手动浏览窗口让位
    if not account_manager.mark_login_started(account_id):
        raise HTTPException(status_code=409, detail="该账号正在登录流程中，请勿重复发起")

    asyncio.create_task(_do_login(account_id, adapter))
    return {
        "account_id": account_id,
        "status": "login_pending",
        "message": "已打开登录窗口，请在浏览器中完成扫码登录",
        "poll_url": f"/api/v1/accounts/{account_id}/status",
    }


async def _do_login(account_id: str, adapter):
    try:
        account = await account_manager.get_account(account_id)
        ok = await adapter.login(account_manager.to_context(account))
        if ok:
            await account_manager.update_account(account_id, status="active", last_login_at=now_iso())
            await account_manager.save_cookie_snapshot(account_id)  # 登录成功自动刷新快照
    except Exception as exc:  # 浏览器异常（如内核未安装）不改动账号状态，仅日志
        from app.services.task_executor import logger
        logger.error("登录流程异常（%s）：%s", account_id, friendly_error(exc))
    finally:
        account_manager.clear_login_started(account_id)


@router.post("/{account_id}/browse")
async def toggle_browser(account_id: str):
    """打开/关闭手动浏览窗口：不自动关闭（区别于登录窗口），用户关窗或再次调用结束。"""
    account = await _get_account_or_404(account_id)
    _require_adapter(account["platform"])
    from app.services import browser

    if browser.is_busy(account.get("profile_path") or "") and not browser.is_manual_open(account_id):
        raise HTTPException(status_code=409, detail="浏览器正被登录/抓取占用，请稍后再试")
    adapter = registry.get_adapter(account["platform"])
    result = await browser.open_manual(account_id, account["profile_path"], adapter.home_url)
    return {"account_id": account_id, **result}


@router.get("/{account_id}/browse")
async def browser_status(account_id: str):
    """手动浏览窗口是否打开（前端恢复按钮状态用）。"""
    await _get_account_or_404(account_id)
    from app.services import browser

    return {"account_id": account_id, "opened": browser.is_manual_open(account_id)}


@router.get("/{account_id}/cookies")
async def get_account_cookies(account_id: str):
    """读取浏览器 profile 的 cookie 列表（通用，不依赖平台适配器）并存快照到 sqlite。"""
    account = await _get_account_or_404(account_id)
    from app.services import browser

    if browser.is_busy(account.get("profile_path") or ""):
        raise HTTPException(status_code=409, detail="浏览器正被登录/抓取占用，请稍后再试")
    try:
        snap = await asyncio.wait_for(
            account_manager.save_cookie_snapshot(account_id), timeout=90
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=friendly_error(exc))
    if snap is None:
        raise HTTPException(status_code=503, detail="cookie 读取失败，详见服务日志")
    return {"account_id": account_id, **snap, "saved": True}


@router.get("/{account_id}/status")
async def login_status(account_id: str):
    """检查登录态：打开 profile 检查关键 cookie，并同步修正账号 status。

    若该账号的浏览器正被登录/抓取占用，直接快速返回（不排队开浏览器），
    避免登录等待期间轮询请求在 profile 锁上堆积、结束后集中弹出浏览器窗口。
    """
    account = await _get_account_or_404(account_id)
    adapter = _require_adapter(account["platform"])
    from app.services import browser

    if browser.is_busy(account.get("profile_path") or ""):
        return {
            "account_id": account_id,
            "logged_in": None,
            "status": account["status"],
            "logging_in": account_manager.is_logging_in(account_id),
            "busy": True,
            "last_login_at": account.get("last_login_at"),
            "checked_at": now_iso(),
        }
    try:
        logged_in = await asyncio.wait_for(
            adapter.check_login_status(account_manager.to_context(account)), timeout=90
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=friendly_error(exc))

    status = account["status"]
    if logged_in and status == "expired":
        status = (await account_manager.update_account(account_id, status="active"))["status"]
    elif not logged_in and status == "active":
        status = (await account_manager.update_account(account_id, status="expired"))["status"]

    return {
        "account_id": account_id,
        "logged_in": logged_in,
        "status": status,
        "logging_in": account_manager.is_logging_in(account_id),
        "last_login_at": account.get("last_login_at"),
        "checked_at": now_iso(),
    }
