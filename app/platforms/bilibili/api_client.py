"""Bilibili 收藏 API 直连客户端。

Bilibili 接口不做客户端 TLS 指纹强校验，这里沿用抖音 api_client 的
curl_cffi impersonate="chrome" 直连模式：登录态复用账号浏览器 profile
（起一次无头 Chromium 读出 cookies 后关闭），后续请求全部走纯 HTTP，
避免每次操作都占用浏览器会话。

写操作（批量删除收藏等）为 POST 表单，csrf 参数取 cookie 中 bili_jct 的值。
"""
import asyncio
import json
import logging
from datetime import datetime
from urllib.parse import urlencode

from curl_cffi import requests

from app.services import browser
from . import constants
from .parser import parse_folder_list, parse_resource_list
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.bilibili.api")

_HEADERS = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9",
    "origin": "https://space.bilibili.com",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


async def profile_cookie_header(profile_path: str) -> str:
    """从持久化浏览器 profile 读取 cookies 拼 cookie 头。

    无登录 cookie 时抛 LoginExpiredError（与浏览器模式同一判定）。
    统一走 browser.session()：channel/并发上限/同 profile 串行锁一处维护，
    避免与抓取会话同时打开同一 profile。
    """
    async with browser.session(profile_path, headless=True) as ctx:
        cookies = await ctx.cookies()
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("Bilibili 登录态缺失（profile 无 SESSDATA），请重新扫码登录")
    return header


def _cookie_value(cookie_header: str, name: str) -> str:
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def csrf_from_cookie_header(cookie_header: str) -> str:
    """写接口的 csrf token 即 cookie bili_jct 的值；缺失视为登录态不完整。"""
    value = _cookie_value(cookie_header, "bili_jct")
    if not value:
        raise LoginExpiredError("Bilibili cookie 中无 bili_jct（csrf token），请重新扫码登录")
    return value


def _referer(cookie_header: str, media_id: str = "") -> str:
    """space 收藏夹页 referer；mid 取 cookie DedeUserID（与抓包一致）。"""
    mid = _cookie_value(cookie_header, "DedeUserID")
    base = f"https://space.bilibili.com/{mid}/favlist" if mid else "https://space.bilibili.com/"
    return f"{base}?fid={media_id}&ftype=create" if media_id else base


def fetch_resource_list_page(cookie_header: str, media_id: str, pn: int = 1,
                             ps: int = constants.PAGE_SIZE) -> dict:
    """拉取一页收藏夹内容（GET fav/resource/list，同步阻塞，异步侧用 asyncio.to_thread 调用）。

    返回 parse_resource_list 的结果 {items, has_more, total, owner, favorite}。
    """
    params = {
        "media_id": media_id, "pn": pn, "ps": ps,
        "keyword": "", "order": "mtime", "type": 0, "tid": 0, "platform": "web",
    }
    response = requests.get(
        constants.FAV_RESOURCE_LIST_API + "?" + urlencode(params),
        headers={**_HEADERS, "referer": _referer(cookie_header), "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"resource/list 返回错误 code={payload.get('code')}："
            f"{payload.get('message') or payload.get('msg')}"
        )
    return parse_resource_list(payload.get("data") or {})


def fetch_folder_list(cookie_header: str, up_mid: str) -> list[dict]:
    """拉取用户的收藏夹列表（GET fav/folder/created/list-all，同步阻塞）。

    返回 parse_folder_list 的 folders：[{media_id, title, media_count}]。
    """
    response = requests.get(
        constants.FAV_FOLDER_LIST_API + "?" + urlencode({"up_mid": up_mid}),
        headers={**_HEADERS, "referer": _referer(cookie_header), "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"folder/list 返回错误 code={payload.get('code')}："
            f"{payload.get('message') or payload.get('msg')}"
        )
    return parse_folder_list(payload.get("data") or {})["folders"]


def folder_edit(cookie_header: str, media_id: str, title: str, intro: str = "",
                privacy: int = 0, cover: str = "") -> dict:
    """编辑收藏夹（POST fav/folder/edit，urlencoded，同步阻塞）。

    cover 必传：接口缺省会清空封面，调用方应先取当前值回填；
    privacy 0=公开 1=私密；code != 0 视为失败抛 RuntimeError。
    """
    body = urlencode({
        "media_id": media_id, "title": title, "intro": intro,
        "privacy": privacy, "cover": cover,
        "csrf": csrf_from_cookie_header(cookie_header),
    })
    logger.info("folder_edit 请求：media_id=%s title=%s privacy=%d", media_id, title, privacy)
    response = requests.post(
        constants.FAV_FOLDER_EDIT_API,
        data=body,
        headers={
            **_HEADERS,
            "content-type": "application/x-www-form-urlencoded",
            "referer": _referer(cookie_header, media_id),
            "cookie": cookie_header,
        },
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"编辑收藏夹失败：code={payload.get('code')} "
            f"message={payload.get('message') or payload.get('msg')}"
        )
    return payload


def folder_del(cookie_header: str, media_ids: list[str]) -> dict:
    """删除收藏夹（POST fav/folder/del，multipart 表单，同步阻塞）。

    media_ids 支持一次删多个（逗号拼接）；默认收藏夹服务端会拒绝。
    curl_cffi 不支持 requests 的 files=，multipart body 手动拼接
    （字段无 filename，与网页端抓包一致）。
    """
    form = {
        "media_ids": ",".join(media_ids),
        "platform": "web",
        "csrf": csrf_from_cookie_header(cookie_header),
    }
    boundary = "----WebKitFormBoundaryFavAPI"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
        for key, value in form.items()
    ]
    logger.info("folder_del 请求：media_ids=%s", form["media_ids"])
    response = requests.post(
        constants.FAV_FOLDER_DEL_API,
        data="".join(parts) + f"--{boundary}--\r\n",
        headers={
            **_HEADERS,
            "content-type": f"multipart/form-data; boundary={boundary}",
            "referer": _referer(cookie_header),
            "cookie": cookie_header,
        },
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"删除收藏夹失败：code={payload.get('code')} "
            f"message={payload.get('message') or payload.get('msg')}"
        )
    return payload


def batch_del_page(cookie_header: str, media_id: str, resources: list) -> dict:
    """删除单批收藏（POST fav/resource/batch-del，同步阻塞）。

    resources 为 (resource_id, type) 列表（视频 type=2，来源 resource/list
    每条的 id/type 字段），拼成 "id:type,id:type"；
    code != 0 视为失败抛 RuntimeError。
    """
    body = urlencode({
        "resources": ",".join(f"{rid}:{rtype}" for rid, rtype in resources),
        "media_id": media_id,
        "platform": "web",
        "csrf": csrf_from_cookie_header(cookie_header),
    })
    logger.info("batch_del 请求：media_id=%s 条数=%d", media_id, len(resources))
    response = requests.post(
        constants.FAV_BATCH_DEL_API,
        data=body,
        headers={
            **_HEADERS,
            "content-type": "application/x-www-form-urlencoded",
            "referer": _referer(cookie_header, media_id),
            "cookie": cookie_header,
        },
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"删除收藏失败：code={payload.get('code')} "
            f"message={payload.get('message') or payload.get('msg')}"
        )
    return payload


async def batch_del_multi(cookie_header: str, media_id: str, resources: list,
                          on_progress=None) -> dict:
    """批量删除收藏：按 BATCH_DEL_SIZE 分批执行。

    返回 {total, batches, deleted}；on_progress(info: dict) 逐批回调进度：
    {"batch_no", "total_batches", "done", "ids"}（done 为累计删除条数）。
    """
    batches = [resources[i:i + constants.BATCH_DEL_SIZE]
               for i in range(0, len(resources), constants.BATCH_DEL_SIZE)]
    deleted_total = 0
    for i, chunk in enumerate(batches, start=1):
        await asyncio.to_thread(batch_del_page, cookie_header, media_id, chunk)
        deleted_total += len(chunk)
        logger.info("batch_del 第 %d/%d 批：%d 条（累计 %d）", i, len(batches), len(chunk), deleted_total)
        if on_progress:
            await on_progress({
                "batch_no": i, "total_batches": len(batches), "done": deleted_total,
                "ids": [str(rid) for rid, _ in chunk],
            })
        if i < len(batches):
            await asyncio.sleep(constants.BATCH_DEL_INTERVAL_SEC)
    return {"total": len(resources), "batches": len(batches), "deleted": deleted_total}


def _resource_pair(item: dict):
    """从 parse_media 条目的 raw_data 提取 batch-del 所需 (resource_id, type)。"""
    try:
        media = json.loads(item.get("raw_data") or "{}")
    except ValueError:
        return None
    rid, rtype = media.get("id"), media.get("type")
    if rid is None or rtype is None:
        return None
    return str(rid), int(rtype)


def _oldest_collected(items: list[dict]):
    """本页可解析的最早收藏时间（列表按收藏时间倒序，即本页最后一条）；无有效时间返回 None。"""
    oldest = None
    for it in items:
        raw = it.get("collected_at")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if oldest is None or ts < oldest:
            oldest = ts
    return oldest


async def cancel_fav_by_window(cookie_header: str, dt_from, dt_to, media_id: str = "",
                               on_progress=None, max_delete: int = 0) -> dict:
    """完整扫描收藏夹，按【收藏于】(fav_time → collected_at) 过滤并批量删除。

    resource/list 按 order=mtime（收藏时间倒序）pn 偏移翻页：删除会使后续页
    前移错位，必须先扫描完收集全部资源再统一 batch-del（与抖音按服务端
    cursor 边拉边删不同）。media_id 为空时遍历全部收藏夹（up_mid 取 cookie
    DedeUserID）。dt_from 存在时可提前终止：本页最早收藏时间已早于下界，
    后续页更旧不可能命中。
    max_delete > 0 时最多删除该数量（小批量验证用）。
    返回 {matched, deleted, folders, pages, total_fetched, stopped_early}。
    """
    from app.utils import filter_by_date_window

    if media_id:
        folders = [{"media_id": media_id, "title": None, "media_count": None}]
    else:
        up_mid = _cookie_value(cookie_header, "DedeUserID")
        if not up_mid:
            raise LoginExpiredError("cookie 中无 DedeUserID，无法确定收藏夹归属，请指定 media_id")
        folders = await asyncio.to_thread(fetch_folder_list, cookie_header, up_mid)

    matched_by_folder: dict[str, list] = {}
    folder_titles: dict[str, str] = {}
    matched_seen: set[tuple[str, str]] = set()
    pages = total_fetched = 0
    stopped_early = False

    for folder in folders:
        pn = 1
        while True:
            batch = await asyncio.to_thread(
                fetch_resource_list_page, cookie_header, folder["media_id"], pn
            )
            pages += 1
            items = batch["items"]
            total_fetched += len(items)
            if folder["title"] is None:
                folder["title"] = batch["favorite"]["title"]
            folder_titles[folder["media_id"]] = folder["title"] or folder["media_id"]

            pairs = []
            for it in filter_by_date_window(items, dt_from, dt_to):
                pair = _resource_pair(it)
                if pair and (folder["media_id"], pair[0]) not in matched_seen:
                    matched_seen.add((folder["media_id"], pair[0]))
                    pairs.append(pair)
            matched_by_folder.setdefault(folder["media_id"], []).extend(pairs)
            page_lo = _oldest_collected(items)
            if on_progress:
                # 与抖音日期区间取消同款 progress 载荷，前端实时日志直接可读
                await on_progress({
                    "type": "progress",
                    "folder": folder_titles[folder["media_id"]], "page": pn,
                    "oldest_collected_at": page_lo.isoformat(timespec="seconds") if page_lo else None,
                    "matched_this_page": len(pairs), "canceled": 0,
                    "total_fetched": total_fetched,
                })

            if not batch["has_more"]:
                break
            if dt_from is not None:
                if page_lo and page_lo < dt_from:
                    logger.info("收藏夹 %s 第 %d 页最早收藏时间(%s)早于下界，提前终止",
                                folder_titles[folder["media_id"]], pn, page_lo)
                    stopped_early = True
                    break
            if pn >= constants.MAX_PAGES:
                logger.warning("收藏夹 %s 翻页达上限 %d 页，提前结束",
                               folder_titles[folder["media_id"]], constants.MAX_PAGES)
                stopped_early = True
                break
            pn += 1
            await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)

    matched_total = sum(len(v) for v in matched_by_folder.values())
    logger.info("扫描完成：%d 个收藏夹 %d 页共 %d 条，命中 %d 条",
                len(folders), pages, total_fetched, matched_total)

    # 删除阶段：pn 偏移翻页已扫完，删除不再影响扫描；max_delete 为全局上限
    deleted_total = 0
    remaining = max_delete
    for f_media_id, pairs in matched_by_folder.items():
        if not pairs:
            continue
        if max_delete and remaining <= 0:
            break
        if max_delete and len(pairs) > remaining:
            logger.info("收藏夹 %s 命中 %d 条，按 max_delete=%d 截断为 %d 条",
                        folder_titles.get(f_media_id, f_media_id), len(pairs), max_delete, remaining)
            pairs = pairs[:remaining]

        async def _del_progress(info: dict):
            if on_progress:
                await on_progress({
                    "type": "progress",
                    "folder": folder_titles.get(f_media_id, f_media_id), **info,
                })

        result = await batch_del_multi(cookie_header, f_media_id, pairs, on_progress=_del_progress)
        deleted_total += result["deleted"]
        remaining -= result["deleted"]

    return {
        "matched": matched_total,
        "deleted": deleted_total,
        "folders": [{"media_id": f["media_id"], "title": f.get("title")} for f in folders],
        "pages": pages,
        "total_fetched": total_fetched,
        "stopped_early": stopped_early,
    }
