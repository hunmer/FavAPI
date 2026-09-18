"""快手收藏/点赞列表 API 客户端。

快手 Web 对 /rest/v/* 接口启用 __NS_hxfalcon 签名强校验（缺失/伪造一律
result=50"签名验证失败"，2026-09 实测；kww header 则不校验）。签名由站点
bundle 内的 JS VM（内部变量 Jose）生成，已剥离到同目录 sig_vm.js，经
sig4.cjs（Node CLI）离线生成 —— 无需浏览器，纯 HTTP 直连。

签名输入 = 接口 path + "caver=" + POST JSON body（见 sig4.cjs 文件头）。
登录态复用账号的浏览器 profile：起一次无头 Chromium 读出 cookies 后关闭，
后续请求全部走 curl_cffi 直连（impersonate="chrome"）。
"""
import asyncio
import json
import logging
import subprocess
from pathlib import Path

from curl_cffi import requests

from app.services import browser
from . import constants
from .parser import (
    parse_download_links,
    parse_feeds_page,
    parse_followings_page,
    parse_profile,
    parse_video_detail,
)
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.kuaishou.api")

_PLATFORM_DIR = Path(__file__).parent

_HEADERS = {
    "accept": "application/json",
    "accept-language": "zh-CN,zh;q=0.9",
    "referer": "https://www.kuaishou.com/",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
}


class SignError(RuntimeError):
    """签名环境问题（缺 Node / 签名脚本失败），调用方须原样上抛，不得当业务失败吞掉。"""


def sign(url_path: str, body: dict | None = None) -> str:
    """调用 sig4.cjs（Node）生成 __NS_hxfalcon 签名（同步阻塞）。"""
    payload = json.dumps({"url": url_path, "body": body or {}})
    try:
        out = subprocess.run(
            ["node", str(_PLATFORM_DIR / constants.SIG_SCRIPT)],
            input=payload, capture_output=True, text=True, timeout=15,
            cwd=str(_PLATFORM_DIR),
        )
    except FileNotFoundError as exc:
        raise SignError(
            "生成快手签名需要 Node.js，但未找到 node 命令。"
            "请安装 Node.js >= 16（https://nodejs.org，或 brew install node / winget install OpenJS.NodeJS）后重试"
        ) from exc
    if out.returncode != 0:
        raise SignError(f"快手签名生成失败：{out.stderr.strip()[:200]}")
    return out.stdout.strip()


def _check_result(data: dict, api: str) -> dict:
    """result != 1 时抛错；50=签名失败（VM 需更新），其余多为登录/参数问题。"""
    if not isinstance(data, dict):
        raise RuntimeError(f"{api} 返回异常响应：{str(data)[:100]}")
    if data.get("result") != 1:
        result = data.get("result")
        msg = data.get("error_msg") or ""
        if result == 50:
            raise RuntimeError(f"{api} 签名验证失败（result=50），sig_vm.js 可能已过期，需更新")
        raise RuntimeError(f"{api} 返回错误 result={result} {msg}".strip())
    return data


def _get(cookie_header: str, path: str) -> dict:
    sig = sign(path, None)
    r = requests.get(
        "https://www.kuaishou.com" + path,
        params={"__NS_hxfalcon": sig, "caver": "2"},
        headers={**_HEADERS, "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    r.raise_for_status()
    return _check_result(r.json(), path)


def _post(cookie_header: str, path: str, body: dict, signed: bool = True) -> dict:
    """POST JSON 接口；signed=False 用于不在 __NS_hxfalcon 签名白名单的接口。"""
    params = {}
    if signed:
        params = {"__NS_hxfalcon": sign(path, body), "caver": "2"}
    r = requests.post(
        "https://www.kuaishou.com" + path,
        params=params,
        data=json.dumps(body, separators=(",", ":")),
        headers={**_HEADERS, "content-type": "application/json",
                 "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    r.raise_for_status()
    return _check_result(r.json(), path)


def _site_cookies(cookies: list[dict]) -> list[dict]:
    """筛选会随请求发往 www.kuaishou.com 的 cookie（复刻浏览器 domain 匹配）。

    profile 里常混入 live.kuaishou.com（直播，可能登录了另一账号）与
    id.kuaishou.com（登录页）的 cookie；全部拼入会出现多个 userId 导致
    服务端 result=109，必须按 domain 匹配规则过滤。
    """
    matched = []
    for c in cookies:
        domain = str(c.get("domain") or "").lstrip(".")
        if domain in ("kuaishou.com", "www.kuaishou.com") or (
                domain.endswith(".kuaishou.com") and "www.kuaishou.com".endswith(domain)):
            matched.append(c)
    return matched


async def profile_cookie_header(profile_path: str) -> str:
    """从持久化浏览器 profile 读取 kuaishou.com cookies 拼 cookie 头。

    无登录 cookie（kuaishou.server.webday7_st）时抛 LoginExpiredError。
    """
    async with browser.session(profile_path, headless=True) as ctx:
        cookies = await ctx.cookies()
    cookies = _site_cookies(cookies)
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("快手登录态缺失（profile 无 kuaishou.server.webday7_st），请重新扫码登录")
    return header


def fetch_profile(cookie_header: str) -> dict:
    """获取当前登录用户信息（GET /rest/v/profile/get，同步阻塞）。

    返回 parser.parse_profile 结果 {eid, user_id, user_name, fans, follows, ...}；
    eid 是收藏列表接口的 userId 入参。
    """
    return parse_profile(_get(cookie_header, "/rest/v/profile/get"))


def fetch_collect_page(cookie_header: str, user_eid: str, pcursor: str = "") -> dict:
    """拉取一页收藏列表（POST /rest/v/collect/list，同步阻塞）。

    pcursor 为上一页响应返回的游标（首页传空串）；
    返回 parse_feeds_page 的结果 {items, pcursor, has_more}。
    """
    data = _post(cookie_header, "/rest/v/collect/list",
                 {"userId": user_eid, "pcursor": pcursor, "page": "collect"})
    return parse_feeds_page(data)


def fetch_like_page(cookie_header: str, pcursor: str = "") -> dict:
    """拉取一页点赞列表（POST /rest/v/feed/liked，同步阻塞），结构与收藏页同构。"""
    data = _post(cookie_header, "/rest/v/feed/liked", {"pcursor": pcursor, "page": "profile"})
    return parse_feeds_page(data)


def fetch_followings_page(cookie_header: str, pcursor: str = "") -> dict:
    """拉取一页关注列表（POST /rest/v/relation/fol，同步阻塞）。

    pcursor 首页传空串，末页返回 "no_more"。接口在 __NS_hxfalcon 签名
    白名单内：缺失签名不报错而是静默返回空列表 + no_more（2026-09 实测），
    必须带签名请求。返回 parse_followings_page 结果
    {items, pcursor, has_more}，items 为 follows 体系统一关注人结构。
    """
    data = _post(cookie_header, "/rest/v/relation/fol",
                 {"pcursor": pcursor, "ftype": 1})
    return parse_followings_page(data)


def fetch_profile_feed_page(cookie_header: str, user_id: str,
                            pcursor: str = "") -> dict:
    """拉取一页博主主页作品（POST /rest/v/profile/feed，同步阻塞）。

    user_id 为博主 eid（即关注列表条目的 user_id）；body 与 collect/list
    同构但键名为下划线 user_id，需 __NS_hxfalcon 签名；响应 feeds 结构
    与 collect/list 同构，复用 parse_feeds_page。
    """
    data = _post(cookie_header, "/rest/v/profile/feed",
                 {"user_id": user_id, "pcursor": pcursor, "page": "profile"})
    return parse_feeds_page(data)


def fetch_photo_detail(cookie_header: str, photo_id: str) -> dict:
    """按 photo_id 拉取视频详情并解析可下载直链（POST /graphql，同步阻塞）。

    visionVideoDetail 走 graphql 网关，不在 __NS_hxfalcon 签名白名单（2026-09
    实测直连即可，kww header 亦可省）；变量仅需 photoId + page="detail"。
    返回 parse_video_detail 结果 + {"links": [{url, label, ext, kind, width, height}]}，
    links 首项为推荐地址（H.264 直链，兼容性最好；H.265 高画质档置后）。
    """
    body = {
        "operationName": "visionVideoDetail",
        "variables": {"photoId": photo_id, "page": "detail"},
        "query": constants.VIDEO_DETAIL_QUERY,
    }
    logger.info("fetch_photo_detail 请求：photo_id=%s", photo_id)
    r = requests.post(
        constants.GRAPHQL_URL,
        data=json.dumps(body, separators=(",", ":")),
        headers={**_HEADERS, "accept": "*/*", "origin": "https://www.kuaishou.com",
                 "content-type": "application/json", "cookie": cookie_header},
        impersonate="chrome", timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    detail = (data.get("data") or {}).get("visionVideoDetail") or {}
    if data.get("errors") or detail.get("status") != 1 or not (detail.get("photo") or {}).get("id"):
        raise RuntimeError(
            f"visionVideoDetail 返回错误：status={detail.get('status')} "
            f"errors={str(data.get('errors'))[:120]}（作品可能已删除或设为私密）")
    result = parse_video_detail(data)
    result["links"] = parse_download_links(data)
    if not result["links"]:
        raise RuntimeError("详情响应无可下载内容（作品可能已删除或设为私密）")
    return result


def set_collect(cookie_header: str, photo_id: str, author_user_id: str = "",
                collect: bool = True) -> dict:
    """收藏 / 取消收藏单个视频（POST /rest/v/photo/collect，同步阻塞）。

    collect=True → collect=1 收藏，False → collect=2 取消；操作幂等。
    写接口不在 __NS_hxfalcon 签名白名单（2026-09 实测，直连即可）；
    作者 userId 服务端不校验，已知则带上与浏览器行为一致。
    """
    body = {"photoId": photo_id, "collect": 1 if collect else 2}
    if author_user_id:
        body["userId"] = author_user_id
    return _post(cookie_header, "/rest/v/photo/collect", body, signed=False)


def set_like(cookie_header: str, photo_id: str, author_user_id: str = "",
             like: bool = True) -> dict:
    """点赞 / 取消点赞单个视频（POST /rest/v/photo/like，同步阻塞）。

    like=True → cancel=0 点赞，False → cancel=1 取消；操作幂等。
    exp_tag 服务端不校验可省；响应含 liked_remain_count（当日剩余点赞数）。
    """
    body = {"cancel": 0 if like else 1, "photo_id": photo_id}
    if author_user_id:
        body["user_id"] = author_user_id
    return _post(cookie_header, "/rest/v/photo/like", body, signed=False)


async def execute_item_actions(cookie_header: str, items: list[dict], action,
                                on_progress=None, label: str = "",
                                stop_on_quota: bool = False) -> dict:
    """逐条执行单视频写操作（action(cookie, photo_id, author_id)，enable 语义由调用方绑定）。

    items: [{photo_id, author_id}]；间隔 WRITE_INTERVAL_SEC 防风控。
    stop_on_quota=True（批量点赞）时，响应 liked_remain_count 归零即停止。
    on_progress({"done", "total"}) 逐条回调。
    返回 {total, done, stopped_reason?, liked_remain_count?}。
    """
    done = 0
    result: dict = {"total": len(items), "done": 0}
    for i, item in enumerate(items, start=1):
        data = await asyncio.to_thread(
            action, cookie_header, item["photo_id"], item.get("author_id") or "")
        done += 1
        remain = data.get("liked_remain_count")
        if isinstance(remain, int):
            result["liked_remain_count"] = remain
        if on_progress:
            await on_progress({"done": done, "total": len(items)})
        logger.info("%s 第 %d/%d 条：%s", label, i, len(items), item["photo_id"])
        if stop_on_quota and isinstance(remain, int) and remain <= 0:
            result["stopped_reason"] = f"当日点赞次数已用完（liked_remain_count=0），剩余 {len(items) - done} 条未执行"
            break
        if i < len(items):
            await asyncio.sleep(constants.WRITE_INTERVAL_SEC)
    result["done"] = done
    return result


async def _fetch_paged(fetch_page, count: int, on_batch, label: str):
    """按 pcursor 游标翻页共用循环（fetch_page(pcursor) → 单页 dict）。"""
    collected: list[dict] = []
    pcursor = ""
    page = 0
    while True:
        batch = await asyncio.to_thread(fetch_page, pcursor)
        page += 1
        collected.extend(batch["items"])
        logger.info("%s 第 %d 页：%d 条，累计 %d，has_more=%s",
                    label, page, len(batch["items"]), len(collected), batch["has_more"])
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        pcursor = batch["pcursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


async def fetch_collect(cookie_header: str, user_eid: str, count: int, on_batch=None):
    """翻页拉取收藏列表，直到取满 count（0=全部）或 pcursor=no_more。"""
    return await _fetch_paged(
        lambda cur: fetch_collect_page(cookie_header, user_eid, cur),
        count, on_batch, "collect")


async def fetch_like(cookie_header: str, count: int, on_batch=None):
    """翻页拉取点赞列表，直到取满 count（0=全部）或 pcursor=no_more。"""
    return await _fetch_paged(
        lambda cur: fetch_like_page(cookie_header, cur),
        count, on_batch, "liked")


async def fetch_followings(cookie_header: str, count: int = 0, on_batch=None):
    """翻页拉取关注列表，直到取满 count（0=全部）或 pcursor=no_more。"""
    return await _fetch_paged(
        lambda cur: fetch_followings_page(cookie_header, cur),
        count, on_batch, "followings")


async def fetch_profile_feed(cookie_header: str, user_id: str, count: int = 0,
                             on_batch=None):
    """翻页拉取博主主页作品，直到取满 count（0=全部）或 pcursor=no_more。"""
    return await _fetch_paged(
        lambda cur: fetch_profile_feed_page(cookie_header, user_id, cur),
        count, on_batch, "profile_feed")


def resolve_user_eid(cookie_header: str) -> str:
    """解析收藏列表所需的用户 eid：profile/get 响应优先，cookie eid 兜底。"""
    try:
        profile = fetch_profile(cookie_header)
        if profile.get("eid"):
            return profile["eid"]
    except SignError:
        raise  # 缺 Node 等环境问题：后续签名必然失败，直接暴露真实原因
    except (RuntimeError, ValueError):
        logger.warning("profile/get 获取 eid 失败，回退 cookie eid", exc_info=True)
    for kv in cookie_header.split("; "):
        name, _, value = kv.partition("=")
        if name == "eid" and value:
            return value
    raise RuntimeError("无法解析用户 eid（profile/get 与 cookie 均失败），请重新登录快手")
