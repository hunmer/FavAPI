"""特别关注（follows）API：关注列表拉取 / 博主管理与分组 / 作品同步 / 播放与已读。"""
import asyncio
import logging
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.database import db
from app.platforms.base import LoginExpiredError
from app.platforms import registry
from app.platforms.douyin import api_client as douyin_api
from app.services import account_manager
from app.services import data_store
from app.services import follow_store
from app.services.follow_store import (
    MEDIA_UA,
    avatar_local_path,
    download_avatar,
    is_allowed_media_url,
)
from app.services.task_executor import friendly_error
from app.utils import now_iso

logger = logging.getLogger("favapi.follows")

router = APIRouter(prefix="/api/v1/follows", tags=["follows"])

# 作品入库来源标记（favorites.source；与收藏/喜欢/稍后再看列表平行）
SOURCE_SPECIAL = "特别关注"


# ---------- 模型 ----------

class FollowAuthorCreate(BaseModel):
    sec_uid: str
    account_id: str = ""
    platform: str = "douyin"
    uid: str = ""
    nickname: str = ""
    unique_id: str = ""
    avatar_url: str = ""
    signature: str = ""
    follower_count: int | None = None
    group_name: str = ""


class FollowAuthorUpdate(BaseModel):
    group_name: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    follower_count: int | None = None


class FollowSyncBody(BaseModel):
    account_id: str = ""      # 缺省逐博主用其添加账号
    sec_uids: list[str] = Field(default_factory=list)  # 空 = 全部博主
    count: int = 10           # 每位博主拉取的最新作品数


# ---------- 公共 ----------

async def _get_account_or_404(account_id: str) -> dict:
    account = await account_manager.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"账号不存在：{account_id}")
    if account["status"] == "disabled":
        raise HTTPException(status_code=400, detail=f"账号 {account_id} 已禁用，请先启用")
    return account


async def _douyin_cookie(account_id: str) -> str:
    """取账号 profile cookie；登录失效时标记 expired 并抛 409。"""
    account = await _get_account_or_404(account_id)
    if registry.get_adapter("douyin") is None:
        raise HTTPException(status_code=400, detail="抖音平台未注册")
    from app.services import browser

    await browser.close_manual(account_id)
    try:
        return await douyin_api.profile_cookie_header(account["profile_path"])
    except LoginExpiredError as exc:
        await account_manager.update_account(account_id, status="expired")
        raise HTTPException(status_code=409, detail=str(exc))


# ---------- 博主管理 ----------

@router.get("/authors")
async def list_follow_authors():
    """特别关注博主列表（含每博主未读作品数与分组）。"""
    authors = await db.query_all(
        "SELECT * FROM follow_authors ORDER BY created_at DESC, sec_uid"
    )
    unread_rows = await db.query_all(
        f"""SELECT fa.sec_uid, COUNT(*) AS unread
            FROM follow_authors fa
            JOIN favorites f ON f.platform = fa.platform AND f.source = ?
            JOIN contents c ON c.content_id = f.content_id AND c.platform = f.platform
            LEFT JOIN follow_reads r ON r.content_id = f.content_id
            WHERE r.content_id IS NULL
              AND (c.author_id = fa.sec_uid OR (fa.uid != '' AND c.author_id = fa.uid))
            GROUP BY fa.sec_uid""",
        (SOURCE_SPECIAL,),
    )
    unread_by_uid = {r["sec_uid"]: r["unread"] for r in unread_rows}
    groups = await db.query_all(
        "SELECT group_name, COUNT(*) AS count FROM follow_authors"
        " WHERE group_name != '' GROUP BY group_name ORDER BY group_name"
    )
    return {
        "authors": [{**a, "unread": unread_by_uid.get(a["sec_uid"], 0)} for a in authors],
        "groups": groups,
    }


@router.post("/authors", status_code=201)
async def add_follow_author(body: FollowAuthorCreate):
    sec_uid = body.sec_uid.strip()
    if not sec_uid.startswith("MS4"):
        raise HTTPException(status_code=400, detail="sec_uid 格式不正确（应以 MS4 开头）")
    if body.account_id:
        await _get_account_or_404(body.account_id)
    existing = await db.query_one(
        "SELECT sec_uid FROM follow_authors WHERE sec_uid = ?", (sec_uid,)
    )
    if existing:
        raise HTTPException(status_code=409, detail="该博主已在特别关注列表中")
    await db.execute(
        """INSERT INTO follow_authors (sec_uid, platform, account_id, uid, nickname,
               unique_id, avatar_url, signature, follower_count, group_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sec_uid, body.platform, body.account_id, body.uid, body.nickname,
         body.unique_id, body.avatar_url, body.signature, body.follower_count,
         body.group_name, now_iso()),
    )
    # 头像立即本地化（失败静默：avatar 路由读取时还会按库中 URL 兜底重试）
    if body.avatar_url:
        await asyncio.to_thread(download_avatar, sec_uid, body.avatar_url)
    return {"sec_uid": sec_uid, "status": "added"}


@router.patch("/authors/{sec_uid}")
async def update_follow_author(sec_uid: str, body: FollowAuthorUpdate):
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有可更新字段")
    cols = ", ".join(f"{k} = ?" for k in fields)
    cur = await db.execute(
        f"UPDATE follow_authors SET {cols} WHERE sec_uid = ?",
        (*fields.values(), sec_uid),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"博主不存在：{sec_uid}")
    # 头像变更时同步刷新本地缓存（失败静默，读取时兜底重试）
    if fields.get("avatar_url"):
        await asyncio.to_thread(download_avatar, sec_uid, fields["avatar_url"])
    return {"sec_uid": sec_uid, "updated": list(fields)}


@router.delete("/authors/{sec_uid}")
async def delete_follow_author(sec_uid: str):
    cur = await db.execute("DELETE FROM follow_authors WHERE sec_uid = ?", (sec_uid,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"博主不存在：{sec_uid}")
    # 顺带清理本地头像文件（缺失静默）
    path = avatar_local_path(sec_uid)
    if path is not None:
        await asyncio.to_thread(path.unlink, True)
    return {"sec_uid": sec_uid, "deleted": True}


@router.get("/authors/{sec_uid}/avatar")
async def follow_author_avatar(sec_uid: str):
    """博主头像统一入口：本地已落盘回文件；未落盘按库中 avatar_url 下载后返回（一次几 KB）。

    浏览器侧长缓存（文件按博主维度覆盖更新）。
    """
    path = avatar_local_path(sec_uid)
    if path is None:
        row = await db.query_one(
            "SELECT avatar_url FROM follow_authors WHERE sec_uid = ?", (sec_uid,)
        )
        url = str((row or {}).get("avatar_url") or "")
        if url.startswith("http"):
            path = await asyncio.to_thread(download_avatar, sec_uid, url)
    if path is None:
        raise HTTPException(status_code=404, detail="博主头像未保存")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


# ---------- 关注列表拉取 ----------

@router.get("/following/{account_id}")
async def fetch_following(account_id: str, count: int = 0):
    """实时拉取账号的关注列表（douyin，只读；count 0 = 全部）。

    sec_user_id 从登录态 cookie 自动提取；返回精简博主字段供前端选择添加。
    """
    count = max(0, min(count, 500))
    cookie_header = await _douyin_cookie(account_id)
    sec_uid = douyin_api.self_sec_uid(cookie_header)
    if not sec_uid:
        raise HTTPException(
            status_code=400,
            detail="无法从登录态提取 sec_user_id，请重新登录抖音账号后再试",
        )
    try:
        followings, has_more = await douyin_api.fetch_following(cookie_header, sec_uid, count)
    except Exception as exc:
        logger.exception("拉取关注列表失败：%s", account_id)
        raise HTTPException(status_code=502, detail=friendly_error(exc))
    return {
        "account_id": account_id,
        "total": len(followings),
        "has_more": has_more,
        "followings": followings,
    }


# ---------- 博主主页作品 ----------

@router.get("/authors/{sec_uid}/posts")
async def author_posts(sec_uid: str, cursor: int = 0, count: int = 18, account_id: str = ""):
    """实时拉取博主发布作品（一页，max_cursor 游标），附已读状态。"""
    author = await db.query_one(
        "SELECT * FROM follow_authors WHERE sec_uid = ?", (sec_uid,)
    )
    use_account = account_id or (author or {}).get("account_id") or ""
    if not use_account:
        raise HTTPException(status_code=400, detail="请指定用于浏览的抖音账号（account_id）")
    cookie_header = await _douyin_cookie(use_account)
    try:
        batch = await asyncio.to_thread(
            douyin_api.fetch_post_page, cookie_header, sec_uid, cursor, max(1, min(count, 50))
        )
    except Exception as exc:
        logger.exception("拉取博主作品失败：%s", sec_uid)
        raise HTTPException(status_code=502, detail=friendly_error(exc))

    ids = [it["content_id"] for it in batch["items"] if it.get("content_id")]
    read_set: set[str] = set()
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        ph = ",".join("?" * len(chunk))
        rows = await db.query_all(
            f"SELECT content_id FROM follow_reads WHERE content_id IN ({ph})", tuple(chunk)
        )
        read_set.update(r["content_id"] for r in rows)
    items = [
        {
            "content_id": it["content_id"],
            "title": it.get("title"),
            "cover_url": it.get("cover_url"),
            "duration": it.get("duration"),
            "published_at": it.get("collected_at"),  # parse_aweme 以 create_time 兜底
            "read": it["content_id"] in read_set,
        }
        for it in batch["items"] if it.get("content_id")
    ]
    return {
        "sec_uid": sec_uid,
        "author": {k: author[k] for k in ("nickname", "avatar_url", "signature", "group_name",
                                          "follower_count", "last_synced_at")} if author else None,
        "items": items,
        "cursor": batch["cursor"],
        "has_more": batch["has_more"],
    }


# ---------- 播放详情 / 已读 ----------

@router.get("/aweme/{aweme_id}")
async def aweme_play_info(aweme_id: str, account_id: str):
    """按作品 ID 拉取播放信息（视频直链 / 图文原图 / 作者 / 统计）。"""
    if not aweme_id.isdigit():
        raise HTTPException(status_code=400, detail="作品 ID 需为纯数字 aweme_id")
    cookie_header = await _douyin_cookie(account_id)
    try:
        info = await asyncio.to_thread(douyin_api.fetch_aweme_play_info, cookie_header, aweme_id)
    except Exception as exc:
        logger.exception("拉取作品播放信息失败：%s", aweme_id)
        raise HTTPException(status_code=502, detail=friendly_error(exc))
    return info


@router.post("/read/{content_id}")
async def mark_read(content_id: str):
    """标记作品为已读（upsert）。"""
    await db.execute(
        "INSERT INTO follow_reads (content_id, read_at) VALUES (?, ?)"
        " ON CONFLICT(content_id) DO UPDATE SET read_at = excluded.read_at",
        (content_id, now_iso()),
    )
    return {"content_id": content_id, "read": True}


@router.delete("/read/{content_id}")
async def unmark_read(content_id: str):
    await db.execute("DELETE FROM follow_reads WHERE content_id = ?", (content_id,))
    return {"content_id": content_id, "read": False}


# ---------- 一键同步最新作品 ----------

@router.post("/sync")
async def sync_follow_posts(body: FollowSyncBody):
    """逐特别关注博主拉取最新作品入库（source=特别关注），并刷新 last_synced_at。"""
    if body.sec_uids:
        ph = ",".join("?" * len(body.sec_uids))
        authors = await db.query_all(
            f"SELECT * FROM follow_authors WHERE sec_uid IN ({ph})", tuple(body.sec_uids)
        )
    else:
        authors = await db.query_all("SELECT * FROM follow_authors ORDER BY created_at")
    if not authors:
        raise HTTPException(status_code=400, detail="特别关注列表为空，请先添加博主")

    count = max(1, min(body.count, 50))
    adapter = registry.get_adapter("douyin")
    results = []
    for a in authors:
        account_id = body.account_id or a["account_id"] or ""
        try:
            account = await _get_account_or_404(account_id) if account_id else None
            if account is None:
                raise ValueError("博主未绑定可用账号，请先在添加时选择账号")
            cookie_header = await douyin_api.profile_cookie_header(account["profile_path"])
            items = await adapter.sync_author_posts(
                account_manager.to_context(account), a, cookie_header, count
            )
            stats = await data_store.save_fetch_result(account, items, source=SOURCE_SPECIAL)
            results.append({
                "sec_uid": a["sec_uid"], "nickname": a["nickname"],
                "status": "ok", "fetched": stats["result_count"],
                "new": stats["new_favorites"],
            })
        except LoginExpiredError as exc:
            if account_id:
                await account_manager.update_account(account_id, status="expired")
            results.append({
                "sec_uid": a["sec_uid"], "nickname": a["nickname"],
                "status": "failed", "detail": str(exc),
            })
        except Exception as exc:
            results.append({
                "sec_uid": a["sec_uid"], "nickname": a["nickname"],
                "status": "failed", "detail": friendly_error(exc),
            })
        await asyncio.sleep(1)  # 逐博主节流防风控

    ok = sum(1 for r in results if r["status"] == "ok")
    new_total = sum(r.get("new", 0) for r in results if r["status"] == "ok")
    return {"total": len(results), "ok": ok, "new": new_total, "results": results}


# ---------- 媒体代理 ----------

@router.get("/media")
def proxy_media(url: str, request: Request):
    """抖音 CDN 媒体流式代理（带 UA/Referer），供前端 <video>/<img> 播放。

    浏览器直连抖音 CDN 会因 referer/UA 被拒，统一走本代理；
    Range 头透传以支持视频进度拖动。同步 def：FastAPI 自动放线程池，不阻塞事件循环。
    """
    if not is_allowed_media_url(url):
        raise HTTPException(status_code=403, detail="不允许的媒体域名")

    headers = {"user-agent": MEDIA_UA, "referer": "https://www.douyin.com/"}
    range_header = request.headers.get("range")
    if range_header:
        headers["range"] = range_header
    try:
        upstream = curl_requests.get(
            url, headers=headers, impersonate="chrome", stream=True, timeout=60
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"媒体拉取失败：{exc}")

    passthrough = ("content-type", "content-length", "content-range",
                   "accept-ranges", "etag", "last-modified")
    out_headers = {k: v for k, v in upstream.headers.items() if k.lower() in passthrough}

    def stream():
        try:
            for chunk in upstream.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return StreamingResponse(stream(), status_code=upstream.status_code, headers=out_headers)
