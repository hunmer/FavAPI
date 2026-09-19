"""特别关注（follows）API：关注列表拉取 / 博主管理与分组 / 作品同步 / 播放与已读。

平台无关：各路由按账号/博主的 platform 经 registry 分发到 adapter 的
follows_* 能力方法（见 platforms/base.py；douyin / bilibili 已实现），
新平台接入只需实现 adapter 方法 + 覆写 follows_api_implemented。
"""
import asyncio
import logging

from curl_cffi import requests as curl_requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.database import db
from app.platforms.base import LoginExpiredError
from app.platforms import registry
from app.services import account_manager
from app.services import data_store
from app.services import follow_store
from app.services.follow_store import (
    MEDIA_UA,
    avatar_local_path,
    download_avatar,
    is_allowed_media_url,
    media_proxy,
    media_referer,
    upgrade_media_url,
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

def _adapter_or_400(platform: str):
    """取支持特别关注体系的平台 adapter；未注册/不支持抛 400。"""
    adapter = registry.get_adapter(platform)
    if adapter is None or not adapter.follows_api_implemented:
        raise HTTPException(status_code=400, detail=f"平台「{platform}」暂不支持特别关注体系")
    return adapter


async def _get_account_or_404(account_id: str) -> dict:
    account = await account_manager.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"账号不存在：{account_id}")
    if account["status"] == "disabled":
        raise HTTPException(status_code=400, detail=f"账号 {account_id} 已禁用，请先启用")
    return account


async def _account_cookie(account_id: str) -> tuple[dict, str]:
    """取账号与其登录 cookie（按账号 platform 分发 adapter）。

    登录失效时标记 expired 并抛 409；返回 (account, cookie_header)。
    """
    account = await _get_account_or_404(account_id)
    adapter = _adapter_or_400(account["platform"])
    from app.services import browser

    await browser.close_manual(account_id)
    try:
        cookie_header = await adapter.follows_profile_cookie(
            account_manager.to_context(account))
    except LoginExpiredError as exc:
        await account_manager.update_account(account_id, status="expired")
        raise HTTPException(status_code=409, detail=str(exc))
    return account, cookie_header


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
    platform = body.platform or "douyin"
    adapter = _adapter_or_400(platform)
    sec_uid = body.sec_uid.strip()
    try:
        adapter.follows_validate_uid(sec_uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
        (sec_uid, platform, body.account_id, body.uid, body.nickname,
         body.unique_id, body.avatar_url, body.signature, body.follower_count,
         body.group_name, now_iso()),
    )
    # 头像立即本地化（失败静默：avatar 路由读取时还会按库中 URL 兜底重试）
    if body.avatar_url:
        await asyncio.to_thread(download_avatar, sec_uid, body.avatar_url)
    return {"sec_uid": sec_uid, "platform": platform, "status": "added"}


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
    """实时拉取账号的关注列表（按账号 platform 分发，只读；count 0 = 全部）。

    当前账号博主主键（douyin sec_uid / bilibili mid）从登录态自动提取；
    返回统一精简博主字段供前端选择添加。
    """
    count = max(0, min(count, 500))
    account, cookie_header = await _account_cookie(account_id)
    adapter = _adapter_or_400(account["platform"])
    self_uid = adapter.follows_self_uid(cookie_header)
    if not self_uid:
        raise HTTPException(
            status_code=400,
            detail=f"无法从登录态提取账号身份，请重新登录{adapter.display_name}账号后再试",
        )
    try:
        followings, has_more = await adapter.follows_fetch_following(
            cookie_header, self_uid, count)
    except Exception as exc:
        logger.exception("拉取关注列表失败：%s", account_id)
        raise HTTPException(status_code=502, detail=friendly_error(exc))
    return {
        "account_id": account_id,
        "platform": account["platform"],
        "total": len(followings),
        "has_more": has_more,
        "followings": followings,
    }


# ---------- 博主主页作品 ----------

@router.get("/authors/{sec_uid}/posts")
async def author_posts(sec_uid: str, cursor: int | str = 0, count: int = 18, account_id: str = ""):
    """实时拉取博主主页作品（一页；cursor 0 = 首页，末页返回 0），附已读状态。

    cursor 兼容两种形态：int（douyin/bilibili/kuaishou 的时间戳或页码）与
    str（xiaohongshu 的不透明十六进制游标，超出 JS 安全整数不可数值化）。
    """
    author = await db.query_one(
        "SELECT * FROM follow_authors WHERE sec_uid = ?", (sec_uid,)
    )
    adapter = _adapter_or_400((author or {}).get("platform") or "douyin")
    use_account = account_id or (author or {}).get("account_id") or ""
    if not use_account:
        raise HTTPException(
            status_code=400,
            detail=f"请指定用于浏览的{adapter.display_name}账号（account_id）",
        )
    account, cookie_header = await _account_cookie(use_account)
    if author and account["platform"] != (author.get("platform") or "douyin"):
        raise HTTPException(
            status_code=400,
            detail=f"浏览账号平台 {account['platform']} 与博主平台 {author.get('platform')} 不一致",
        )
    try:
        # cursor 归一：str 游标原样透传（xiaohongshu），但字符串 "0" 是前端首屏
        # 默认值（FastAPI smart union 把 ?cursor=0 解析为 str），必须归 0 = 首页
        cur = cursor if isinstance(cursor, str) and cursor != "0" else max(0, int(cursor))
        batch = await adapter.follows_fetch_posts_page(
            cookie_header, sec_uid, cur, max(1, min(count, 50)),
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
            "published_at": it.get("collected_at"),  # 投稿列表 collected_at 即发布时间
            "read": it["content_id"] in read_set,
        }
        for it in batch["items"] if it.get("content_id")
    ]
    return {
        "sec_uid": sec_uid,
        "author": {k: author[k] for k in ("platform", "nickname", "avatar_url", "signature",
                                          "group_name", "follower_count", "last_synced_at")} if author else None,
        "items": items,
        "cursor": batch["cursor"],
        "has_more": batch["has_more"],
    }


# ---------- 播放详情 / 已读 ----------

@router.get("/aweme/{aweme_id}")
async def aweme_play_info(aweme_id: str, account_id: str):
    """按作品 ID 拉取播放信息（视频直链 / 图文原图 / 作者 / 统计）。

    aweme_id 泛指平台作品 ID（douyin 数字 aweme_id / bilibili BV 号），按账号平台分发。
    """
    account, cookie_header = await _account_cookie(account_id)
    adapter = _adapter_or_400(account["platform"])
    try:
        info = await adapter.follows_play_info(cookie_header, aweme_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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

async def _select_sync_authors(sec_uids: list[str]) -> list[dict]:
    if sec_uids:
        ph = ",".join("?" * len(sec_uids))
        return await db.query_all(
            f"SELECT * FROM follow_authors WHERE sec_uid IN ({ph})", tuple(sec_uids)
        )
    return await db.query_all("SELECT * FROM follow_authors ORDER BY created_at")


async def _sync_authors_impl(authors: list[dict], count: int, account_id: str = "",
                             on_event=None) -> list[dict]:
    """逐博主按其 platform 分发同步最新作品入库；on_event 逐博主回调进度（/sync 与 SSE 流式共用）。"""
    results = []
    for a in authors:
        platform = a["platform"] or "douyin"
        use_account = account_id or a["account_id"] or ""
        try:
            adapter = registry.get_adapter(platform)
            if adapter is None or not adapter.follows_api_implemented:
                raise ValueError(f"平台「{platform}」暂不支持特别关注同步")
            account = await _get_account_or_404(use_account) if use_account else None
            if account is None:
                raise ValueError("博主未绑定可用账号，请先在添加时选择账号")
            if account["platform"] != platform:
                raise ValueError(f"账号平台 {account['platform']} 与博主平台 {platform} 不一致")
            ctx = account_manager.to_context(account)
            cookie_header = await adapter.follows_profile_cookie(ctx)
            items = await adapter.sync_author_posts(ctx, a, cookie_header, count)
            stats = await data_store.save_fetch_result(account, items, source=SOURCE_SPECIAL)
            results.append({
                "sec_uid": a["sec_uid"], "nickname": a["nickname"],
                "status": "ok", "fetched": stats["result_count"],
                "new": stats["new_favorites"],
            })
        except LoginExpiredError as exc:
            if use_account:
                await account_manager.update_account(use_account, status="expired")
            results.append({
                "sec_uid": a["sec_uid"], "nickname": a["nickname"],
                "status": "failed", "detail": str(exc),
            })
        except HTTPException as exc:
            results.append({
                "sec_uid": a["sec_uid"], "nickname": a["nickname"],
                "status": "failed", "detail": str(exc.detail),
            })
        except Exception as exc:
            results.append({
                "sec_uid": a["sec_uid"], "nickname": a["nickname"],
                "status": "failed", "detail": friendly_error(exc),
            })
        if on_event:
            await on_event(results[-1], len(results), len(authors))
        await asyncio.sleep(1)  # 逐博主节流防风控
    return results


@router.post("/sync")
async def sync_follow_posts(body: FollowSyncBody):
    """逐特别关注博主拉取最新作品入库（source=特别关注），并刷新 last_synced_at。"""
    authors = await _select_sync_authors(body.sec_uids)
    if not authors:
        raise HTTPException(status_code=400, detail="特别关注列表为空，请先添加博主")
    results = await _sync_authors_impl(
        authors, max(1, min(body.count, 50)), body.account_id
    )
    ok = sum(1 for r in results if r["status"] == "ok")
    new_total = sum(r.get("new", 0) for r in results if r["status"] == "ok")
    return {"total": len(results), "ok": ok, "new": new_total, "results": results}


@router.post("/sync/stream")
async def sync_follow_posts_stream(body: FollowSyncBody):
    """SSE 流式一键同步：逐博主推 progress，结束推 done（Header 按钮实时进度用）。

    事件格式 data: {"type": "progress"|"done"|"error", ...}；客户端断开时后台执行自动取消。
    """
    import json

    from fastapi.responses import StreamingResponse

    authors = await _select_sync_authors(body.sec_uids)
    if not authors:
        raise HTTPException(status_code=400, detail="特别关注列表为空，请先添加博主")

    queue: asyncio.Queue = asyncio.Queue()
    results_holder: list[dict] = []  # 逐博主累计（progress 事件里算 ok/new 汇总用）

    async def _run():
        try:
            async def _on_event(result: dict, done_n: int, total_n: int):
                results_holder.append(result)
                ok = sum(1 for r in results_holder if r["status"] == "ok")
                new_n = sum(r.get("new", 0) for r in results_holder if r["status"] == "ok")
                await queue.put({
                    "type": "progress",
                    "done": done_n, "total": total_n,
                    "nickname": result.get("nickname"),
                    "status": result.get("status"),
                    "fetched": result.get("fetched", 0),
                    "new": new_n, "ok": ok,
                })

            results = await _sync_authors_impl(
                authors, max(1, min(body.count, 50)), body.account_id, on_event=_on_event
            )
            ok = sum(1 for r in results if r["status"] == "ok")
            new_total = sum(r.get("new", 0) for r in results if r["status"] == "ok")
            await queue.put({"type": "done", "total": len(results), "ok": ok, "new": new_total,
                             "results": results})
        except Exception as exc:
            logger.exception("流式同步失败")
            await queue.put({"type": "error", "message": friendly_error(exc)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(_run())

    async def sse():
        try:
            while True:
                evt = await queue.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():  # 客户端断开 → 取消后台执行
                task.cancel()

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- 媒体代理 ----------

@router.get("/media")
def proxy_media(url: str, request: Request):
    """平台 CDN 媒体流式代理（带 UA，抖音系另带 referer），供前端 <video>/<img> 播放。

    浏览器直连各平台 CDN 会因 referer/UA 被拒，统一走本代理；
    Range 头透传以支持视频进度拖动。同步 def：FastAPI 自动放线程池，不阻塞事件循环。
    """
    if not is_allowed_media_url(url):
        raise HTTPException(status_code=403, detail="不允许的媒体域名")
    url = upgrade_media_url(url)

    headers = {"user-agent": MEDIA_UA}
    referer = media_referer(url)
    if referer:
        headers["referer"] = referer
    range_header = request.headers.get("range")
    if range_header:
        headers["range"] = range_header
    try:
        upstream = curl_requests.get(
            url, headers=headers, impersonate="chrome", stream=True, timeout=60,
            proxy=media_proxy(url),
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
