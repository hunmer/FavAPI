"""账号管理 API（PRD 3.1）。"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, UploadFile, File
from app import config

from app.models import AccountCreate, AccountOut, AccountUpdate
from app.platforms import registry
from app.services import account_manager
from app.services.task_executor import friendly_error
from app.utils import now_iso

logger = logging.getLogger("favapi.accounts")

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])
_login_tasks: dict[str, asyncio.Task] = {}

@router.post("/{account_id}/wechat-import")
async def upload_wechat_json(account_id: str, file: UploadFile = File(...)):
    account = await _get_account_or_404(account_id)
    if account["platform"] != "wechat":
        raise HTTPException(400, "仅微信收藏账号支持 JSON 导入")
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(400, "仅支持 .json 文件")
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(400, "JSON 文件不能超过 100MB")
    target_dir = config.DATA_DIR / "wechat_imports" / account_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "messages.json"
    target.write_bytes(data)
    return {"json_path": str(target), "filename": file.filename, "size": len(data)}

platforms_router = APIRouter(prefix="/api/v1", tags=["accounts"])


@platforms_router.get("/platforms")
async def list_platforms():
    """全部平台元信息（含是否已实现、支持的 action）。"""
    return {"platforms": registry.platform_infos()}

@platforms_router.post("/platforms/reload")
async def reload_platforms():
    """重新扫描声明式平台目录，便于生产环境增删平台后立即生效。"""
    return {"loaded": registry.load_declarative() , "platforms": registry.platform_infos()}

@router.post("/{account_id}/refresh-profile")
async def refresh_profile(account_id: str):
    account = await _get_account_or_404(account_id)
    adapter = _require_adapter(account["platform"])
    try:
        await adapter.refresh_profile(account_manager.to_context(account))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=friendly_error(exc))
    return {"account_id": account_id, "status": "ok"}


@platforms_router.get("/platforms/{platform}/icon")
async def platform_icon(platform: str):
    """平台图标（platform.json 的 icon 字段指定的文件，位于平台目录内）。"""
    from pathlib import Path

    from fastapi.responses import FileResponse

    adapter = registry.get_adapter(platform)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"未知平台：{platform}")
    base_dir = getattr(adapter, "base_dir", None)
    if not adapter.icon or not base_dir:
        raise HTTPException(status_code=404, detail=f"{adapter.display_name} 未配置图标")
    path = Path(base_dir) / adapter.icon
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"图标文件不存在：{path.name}")
    return FileResponse(path, media_type="image/x-icon")


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


@router.post("/refresh-profile")
async def refresh_all_profiles():
    """批量刷新账号身份信息（昵称/头像/收藏夹）；串行执行避免浏览器并发冲突。"""
    from app.platforms.base import BasePlatformAdapter

    results = []
    for a in await account_manager.list_accounts():
        adapter = registry.get_adapter(a["platform"])
        if adapter is None or type(adapter).refresh_profile is BasePlatformAdapter.refresh_profile:
            results.append({"account_id": a["account_id"], "name": a["name"],
                            "status": "skipped", "detail": "该平台暂不支持身份刷新"})
            continue
        try:
            await adapter.refresh_profile(account_manager.to_context(a))
            results.append({"account_id": a["account_id"], "name": a["name"],
                            "status": "ok", "detail": ""})
        except Exception as exc:
            results.append({"account_id": a["account_id"], "name": a["name"],
                            "status": "failed", "detail": friendly_error(exc)})

    ok = sum(1 for r in results if r["status"] == "ok")
    failed = sum(1 for r in results if r["status"] == "failed")
    if failed:
        logger.warning("批量身份刷新：成功 %d，失败 %d：%s", ok, failed,
                       "; ".join(f"{r['name']}: {r['detail']}" for r in results if r["status"] == "failed"))
    return {"ok": ok, "failed": failed, "results": results}


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

    task = asyncio.create_task(_do_login(account_id, adapter))
    _login_tasks[account_id] = task
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
            try:
                await adapter.refresh_profile(account_manager.to_context(account))  # 回填昵称/头像/收藏夹
            except Exception as exc:
                logger.warning("账号 %s 身份信息回填失败（不影响登录）：%s", account_id, friendly_error(exc))
    except Exception as exc:  # 浏览器异常（如内核未安装）不改动账号状态，仅日志
        logger.error("登录流程异常（%s）：%s", account_id, friendly_error(exc))
    finally:
        account_manager.clear_login_started(account_id)
        _login_tasks.pop(account_id, None)

@router.post("/{account_id}/login/close")
async def close_login(account_id: str):
    await _get_account_or_404(account_id)
    task = _login_tasks.get(account_id)
    if task and not task.done():
        task.cancel()
        return {"account_id": account_id, "closed": True}
    return {"account_id": account_id, "closed": False}


@router.post("/{account_id}/browse")
async def toggle_browser(account_id: str):
    """打开/关闭手动浏览窗口：不自动关闭（区别于登录窗口），用户关窗或再次调用结束。"""
    account = await _get_account_or_404(account_id)
    _require_adapter(account["platform"])
    from app.services import browser

    if browser.is_busy(account.get("profile_path") or "") and not browser.is_manual_open(account_id):
        raise HTTPException(status_code=409, detail="浏览器正被登录/抓取占用，请稍后再试")
    adapter = registry.get_adapter(account["platform"])
    # 声明式平台可将抓取入口 home_url 与手动浏览官网 homepage 分离。
    result = await browser.open_manual(account_id, account["profile_path"], getattr(adapter, "homepage", "") or adapter.home_url)
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
