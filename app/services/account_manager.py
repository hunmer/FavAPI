"""账号（Session）管理：CRUD + 登录流程状态 + cookie 快照 + 身份回填。"""
import json
import logging
import shutil
from pathlib import Path

import httpx

from app import config
from app.database import db
from app.platforms import registry
from app.platforms.base import AccountContext
from app.utils import new_id, now_iso

logger = logging.getLogger("favapi.accounts")

# 账号头像本地存储（各平台 owner.avatar 为带签名 CDN 链接，会过期，落盘后由本服务下发）
AVATARS_DIR = config.DATA_DIR / "uploads" / "account_avatars"
# Content-Type → 扩展名（兜底 .jpg，各平台头像实际均为 jpg/png/webp）
_AVATAR_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def avatar_url(account_id: str) -> str:
    """头像的下发 URL（GET /api/v1/accounts/{id}/avatar）。"""
    return f"/api/v1/accounts/{account_id}/avatar"


def avatar_path(account_id: str) -> Path | None:
    """已落盘的头像文件路径；无则 None。"""
    if not AVATARS_DIR.exists():
        return None
    return next(iter(sorted(AVATARS_DIR.glob(f"{account_id}.*"))), None)


async def _save_avatar_file(account_id: str, url: str) -> bool:
    """下载头像到本地（替换旧文件）；失败仅告警，返回 False。"""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        if not resp.content:
            return False
        ext = _AVATAR_TYPES.get(resp.headers.get("content-type", "").split(";")[0].strip(), ".jpg")
        AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        for old in AVATARS_DIR.glob(f"{account_id}.*"):
            old.unlink(missing_ok=True)
        (AVATARS_DIR / f"{account_id}{ext}").write_bytes(resp.content)
        return True
    except Exception as exc:
        logger.warning("账号 %s 头像下载失败（保留原链，下次刷新重试）：%s", account_id, exc)
        return False


async def save_owner(account_id: str, platform: str, data: dict) -> dict | None:
    """各平台身份回填的统一入口：extra[platform] = data（形如 {"owner": {...}}）。

    owner.avatar 为 http(s) 时先下载落盘防过期，成功后替换为本服务 URL
    （avatar_url）；失败保留原链。账号不存在返回 None。
    """
    row = await get_account(account_id)
    if row is None:
        return None
    owner = data.setdefault("owner", {})
    origin = str(owner.get("avatar") or "").strip()
    if origin.startswith("http") and await _save_avatar_file(account_id, origin):
        owner["avatar"] = avatar_url(account_id)
    extra = row.get("extra") or {}
    extra[platform] = data
    await update_account(account_id, extra=json.dumps(extra, ensure_ascii=False))
    return owner


def owner_avatar(row: dict) -> str | None:
    """从账号行提取统一头像字段 extra.{platform}.owner.avatar（平台间已统一命名）。"""
    platform_data = (row.get("extra") or {}).get(row.get("platform") or "") or {}
    return (platform_data.get("owner") or {}).get("avatar") or None

# 内存态：正在走登录流程的账号（服务重启即清空）
_login_in_progress: set[str] = set()


def mark_login_started(account_id: str) -> bool:
    """标记开始登录；已在登录中返回 False（用于 409 防重入）。"""
    if account_id in _login_in_progress:
        return False
    _login_in_progress.add(account_id)
    return True


def clear_login_started(account_id: str):
    _login_in_progress.discard(account_id)


def is_logging_in(account_id: str) -> bool:
    return account_id in _login_in_progress


def _row_out(row: dict) -> dict:
    out = dict(row)
    try:
        out["extra"] = json.loads(out.get("extra") or "{}")
    except (TypeError, json.JSONDecodeError):
        out["extra"] = {}
    return out


def to_context(row: dict) -> AccountContext:
    return AccountContext(
        account_id=row["account_id"],
        platform=row["platform"],
        name=row.get("name") or "",
        profile_path=row.get("profile_path") or "",
    )


async def create_account(platform: str, name: str, extra: dict | None = None) -> dict:
    info = registry.get_platform_info(platform)
    if info is None:
        raise ValueError(f"未知平台：{platform}（可用：{', '.join(i['platform'] for i in registry.platform_infos())}）")
    if not info["implemented"]:
        raise ValueError(f"{info['display_name']} 平台即将支持，暂不能创建账号")

    account_id = new_id("acc")
    row = {
        "account_id": account_id,
        "platform": platform,
        "name": name or f"{info['display_name']}账号",
        "status": "active",
        "profile_path": str(config.PROFILES_DIR / f"{platform}_{account_id}"),
        "last_login_at": None,
        "last_used_at": None,
        "created_at": now_iso(),
        "extra": json.dumps(extra or {}, ensure_ascii=False),
    }
    await db.execute(
        """INSERT INTO accounts (account_id, platform, name, status, profile_path,
           last_login_at, last_used_at, created_at, extra)
           VALUES (:account_id, :platform, :name, :status, :profile_path,
                   :last_login_at, :last_used_at, :created_at, :extra)""",
        row,
    )
    return _row_out(row)


async def list_accounts() -> list[dict]:
    rows = await db.query_all("SELECT * FROM accounts ORDER BY created_at DESC")
    return [_row_out(r) for r in rows]


async def get_account(account_id: str) -> dict | None:
    row = await db.query_one("SELECT * FROM accounts WHERE account_id = ?", (account_id,))
    return _row_out(row) if row else None


async def update_account(account_id: str, **fields) -> dict | None:
    """更新指定列；字段名由调用方保证合法（API 层已做白名单）。"""
    if not fields:
        return await get_account(account_id)
    cols = ", ".join(f"{k} = ?" for k in fields)
    await db.execute(
        f"UPDATE accounts SET {cols} WHERE account_id = ?",
        (*fields.values(), account_id),
    )
    return await get_account(account_id)


async def delete_account(account_id: str) -> bool:
    row = await get_account(account_id)
    if row is None:
        return False
    # 收藏关系随账号删除；contents 保留（跨账号去重数据）；任务记录保留（历史排查）
    await db.execute("DELETE FROM favorites WHERE account_id = ?", (account_id,))
    await db.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))
    for old in AVATARS_DIR.glob(f"{account_id}.*"):
        old.unlink(missing_ok=True)
    if row.get("profile_path"):
        shutil.rmtree(row["profile_path"], ignore_errors=True)
    return True


async def save_cookie_snapshot(account_id: str, cookies: list[dict] | None = None) -> dict | None:
    """把 cookie 快照写入 accounts.extra.cookies，返回快照（失败返回 None，不抛异常）。

    - cookies 提供时直接存（调用方仍持有浏览器会话时免二次打开）
    - 不提供则无头打开该账号 profile 读取
    """
    account = await get_account(account_id)
    if account is None:
        return None
    try:
        if cookies is None:
            from app.services import browser  # 延迟导入避免循环依赖

            async with browser.session(account["profile_path"], headless=True) as ctx:
                cookies = await ctx.cookies()
        snap = {
            "captured_at": now_iso(),
            "cookies": [
                {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain"),
                    "path": c.get("path"),
                    "expires": c.get("expires"),
                    "secure": bool(c.get("secure")),
                }
                for c in cookies or []
            ],
        }
        extra = account.get("extra") or {}
        extra["cookies"] = snap
        await update_account(account_id, extra=json.dumps(extra, ensure_ascii=False))
        return snap
    except Exception as exc:
        logger.warning("账号 %s cookie 快照保存失败：%s", account_id, exc)
        return None
