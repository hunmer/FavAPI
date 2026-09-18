"""小红书收藏/点赞列表 API 客户端（xhshow 纯算签名 + curl_cffi 直连）。

edith.xiaohongshu.com 的 note 列表接口有 x-s / x-s-common / x-t 签名强校验
（无签名 406；签名与 cookie 环境不一致 300011「账号异常」）。签名由
xhshow 纯算法生成（XYS_ 格式，无需浏览器页面 JS），请求走 curl_cffi 复刻
Chrome TLS/HTTP2 指纹；全程纯 HTTP（读 profile cookies 需起一次无头浏览器）。

实测坑（2026-09）：
- 实际请求 URL 必须与签名内容逐字节一致：query 用 xhshow.build_url 构造
  （逗号不转义）；curl_cffi 的 params= 会把逗号编码成 %2C，签名不匹配直接 406
- cookies 必须以 dict 传给签名：cookie 字符串里带引号的 unread JSON 会让
  SimpleCookie 解析错位，生成的 x-s-common 无效（300011）
- like/page 与 collect/page 均接受 XYS_ 格式；xyw 格式反而被这两个接口拒绝
"""
import asyncio
import logging

from curl_cffi import requests
from xhshow import Xhshow

from app.services import browser
from . import constants
from .parser import parse_collect_page, parse_download_links, parse_following_page
from ..base import LoginExpiredError

logger = logging.getLogger("favapi.xiaohongshu.api")

_signer = Xhshow()

_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "origin": "https://www.xiaohongshu.com",
    "referer": "https://www.xiaohongshu.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
}


async def profile_cookies(profile_path: str) -> dict[str, str]:
    """从持久化浏览器 profile 读取 xiaohongshu cookies（dict，签名与请求共用）。

    无登录 cookie 时抛 LoginExpiredError（与浏览器模式同一判定）。
    """
    async with browser.session(profile_path, headless=True) as ctx:
        cookies = await ctx.cookies()
    if not browser.has_login_cookies(cookies, constants.LOGIN_COOKIE_KEYS):
        raise LoginExpiredError("小红书登录态缺失（profile 无 id_token），请重新扫码登录")
    return {c["name"]: c["value"] for c in cookies if c.get("name")}


def _check(data: dict) -> dict:
    """响应 code 检查；非 0 抛 RuntimeError（300011/300031 单独提示）。"""
    code = data.get("code")
    if code == 300011:
        raise RuntimeError(
            "接口返回 300011 账号异常：多为签名与 cookie 环境不一致或触发风控，"
            "请稍后重试；反复出现请重新扫码登录刷新登录态"
        )
    if code == 300031:
        raise RuntimeError(
            "接口返回 300031 笔记无法浏览：xsec_token 缺失或已失效（HTTP 461），"
            "请重新抓取列表刷新笔记 token 或手动填写"
        )
    if code != 0:
        raise RuntimeError(f"小红书接口返回错误 code={code} msg={data.get('msg')}")
    return data


def _cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _signed_get(cookies: dict[str, str], url: str, params: dict[str, str],
                user_id: str | None = None) -> dict:
    """签名 + 直连 GET，返回响应 JSON。

    URL 用 xhshow.build_url 构造以保证与签名内容逐字节一致（见模块 docstring）。
    """
    sign = _signer.sign_headers_get(url, cookies=cookies, params=params, user_id=user_id)
    response = requests.get(
        _signer.build_url(url, params),
        headers={**_HEADERS, **sign, "cookie": _cookie_header(cookies)},
        impersonate="chrome", timeout=20,
    )
    response.raise_for_status()
    return _check(response.json())


def _signed_post(cookies: dict[str, str], url: str, payload: dict) -> dict:
    """签名 + 直连 POST JSON，返回响应 JSON。

    body 必须用 xhshow.build_json_body 序列化（紧凑、不转义中文），
    与签名的 content string（uri + 紧凑 JSON）逐字节一致；curl_cffi 的
    json= 用默认分隔符（带空格），直接用会签名不匹配被拒。

    非 200 但带 JSON 错误体的响应（feed 详情无效 token 的 461）优先按
    code/msg 映射错误，否则才按 HTTP 状态抛。
    """
    sign = _signer.sign_headers_post(url, cookies=cookies, payload=payload)
    response = requests.post(
        url,
        data=_signer.build_json_body(payload).encode("utf-8"),
        headers={
            **_HEADERS, **sign,
            "content-type": "application/json;charset=UTF-8",
            "cookie": _cookie_header(cookies),
        },
        impersonate="chrome", timeout=20,
    )
    try:
        data = response.json()
    except Exception:
        response.raise_for_status()
        raise RuntimeError(f"小红书接口响应非 JSON（HTTP {response.status_code}）")
    return _check(data)


def fetch_me(cookies: dict[str, str]) -> dict:
    """签名调用 /user/me 返回 data（当前登录用户信息）；游客/未登录返回 {}（同步阻塞）。"""
    data = (_signed_get(cookies, constants.USER_ME_URL, {}) or {}).get("data") or {}
    if data.get("guest") or not data.get("user_id"):
        return {}
    return data


def fetch_note_detail(cookies: dict[str, str], note_id: str, xsec_token: str) -> dict:
    """按 note_id 调 feed 详情接口并解析可下载直链（同步阻塞，异步侧 to_thread 调用）。

    xsec_token 强校验（空/失效 → 461 code=300031）：来自收藏/点赞列表响应
    notes[].xsec_token（已随 raw_data 入库）；xsec_source 实测不校验，固定 pc_feed。
    返回 {"note_id", "links": [{url, label, ext, kind, width, height, size}],
          "author_name", "author_id"}；links 为空抛 RuntimeError。
    """
    data = _signed_post(cookies, constants.NOTE_DETAIL_URL, {
        "source_note_id": note_id,
        "image_formats": ["jpg", "webp", "avif"],
        "extra": {"need_body_topic": "1"},
        "xsec_source": "pc_feed",
        "xsec_token": xsec_token,
    })
    links = parse_download_links(data)
    if not links:
        raise RuntimeError("详情响应无可下载内容（笔记可能已删除或设为私密）")
    note = {}
    for item in (data.get("data") or {}).get("items") or []:
        card = item.get("note_card") or {}
        if card.get("note_id"):
            note = card
            break
    user = note.get("user") or {}
    return {
        "note_id": note_id,
        "links": links,
        "author_name": user.get("nickname"),
        "author_id": str(user.get("user_id") or ""),
    }


def fetch_note_page(cookies: dict[str, str], url: str, user_id: str,
                    cursor: str = "", num: int = 30) -> dict:
    """签名拉取一页 note 列表（like/collect 通用，同步阻塞，异步侧用 asyncio.to_thread）。

    cursor 为上一页响应返回的不透明游标（首页传空串）；
    返回 parse_collect_page 的结果 {items, cursor, has_more, total}。
    """
    params = {
        "num": str(num), "cursor": cursor, "user_id": user_id,
        "image_formats": "jpg,webp,avif", "xsec_token": "", "xsec_source": "",
    }
    data = _signed_get(cookies, url, params, user_id=user_id)
    return parse_collect_page(data)


async def fetch_note_pages(cookies: dict[str, str], url: str, user_id: str,
                           count: int, on_batch=None):
    """按服务端游标翻页拉取 note 列表，直到取满 count（0=全部）或 has_more=false。

    返回 (全部 items, 最后一批的 has_more)。游标为不透明笔记 id，无时间语义，
    不做日期提前终止。
    """
    cursor = ""
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(
            fetch_note_page, cookies, url, user_id, cursor, constants.API_PAGE_COUNT
        )
        page += 1
        collected.extend(batch["items"])
        logger.info(
            "note 列表第 %d 页：%d 条，累计 %d，has_more=%s",
            page, len(batch["items"]), len(collected), batch["has_more"],
        )
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"] or not batch["cursor"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        cursor = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


# ---- 关注列表 / 博主主页笔记（follows 体系数据层，2026-09 实测）----


def fetch_following_page(cookies: dict[str, str], page: int = 1) -> dict:
    """拉取一页关注列表（GET im/web/users/following/all，同步阻塞）。

    IM 通道接口实测不校验 x-s 签名，仍走统一签名链路与浏览器行为一致；
    page/size 偏移翻页，接口无 has_more 字段，末页返回空列表。
    返回 parse_following_page 结果 {items, has_more}，items 为统一关注人结构。
    """
    data = _signed_get(cookies, constants.FOLLOWING_ALL_URL, {
        "page": str(page), "size": str(constants.FOLLOWING_PAGE_SIZE),
    })
    return parse_following_page(data, constants.FOLLOWING_PAGE_SIZE)


async def fetch_followings(cookies: dict[str, str], count: int = 0, on_batch=None):
    """翻页拉取关注列表，直到取满 count（0=全部）或返回空页。

    返回 (全部 items, 最后一批的 has_more)；on_batch({"page", "items"}) 逐页回调。
    """
    collected: list[dict] = []
    page = 1
    while True:
        batch = await asyncio.to_thread(fetch_following_page, cookies, page)
        collected.extend(batch["items"])
        logger.info("followings 第 %d 页：%d 条，累计 %d，has_more=%s",
                    page, len(batch["items"]), len(collected), batch["has_more"])
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"] or not batch["items"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        page += 1
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


def fetch_user_posted_page(cookies: dict[str, str], user_id: str, cursor: str = "",
                           xsec_token: str = "") -> dict:
    """拉取一页博主主页笔记（GET user_posted，同步阻塞）。

    x-s 签名强校验（无签名 406）；xsec_token 为博主访问凭证，实测空串
    亦可访问（2026-09，未在全部博主上验证），有 token（信息流/搜索下发）时
    带上与浏览器行为一致；cursor 为上一页响应返回的不透明游标（首页空串）。
    响应 notes 与 collect/page 同构，复用 parse_collect_page
    → {items, cursor, has_more, total}。
    """
    params = {
        "num": str(constants.API_PAGE_COUNT), "cursor": cursor, "user_id": user_id,
        "image_formats": "jpg,webp,avif", "xsec_token": xsec_token,
        "xsec_source": "pc_feed",
    }
    data = _signed_get(cookies, constants.USER_POSTED_URL, params, user_id=user_id)
    return parse_collect_page(data)


async def fetch_user_posted(cookies: dict[str, str], user_id: str, count: int = 0,
                            on_batch=None):
    """按 cursor 游标翻页拉取博主主页笔记，直到取满 count（0=全部）或 has_more=false。

    返回 (全部 items, 最后一批的 has_more)；on_batch({"page", "items"}) 逐页回调。
    """
    cursor = ""
    collected: list[dict] = []
    page = 0
    while True:
        batch = await asyncio.to_thread(fetch_user_posted_page, cookies, user_id, cursor)
        page += 1
        collected.extend(batch["items"])
        logger.info("user_posted 第 %d 页：%d 条，累计 %d，has_more=%s",
                    page, len(batch["items"]), len(collected), batch["has_more"])
        if on_batch and batch["items"]:
            await on_batch({"page": page, "items": batch["items"]})
        if not batch["has_more"] or not batch["cursor"]:
            return collected, False
        if count and len(collected) >= count:
            return collected, True
        cursor = batch["cursor"]
        await asyncio.sleep(constants.API_PAGE_INTERVAL_SEC)


# ---- 写操作（2026-09 实测：签名校验与读接口同链路，直连可用）----
# 注意三个接口的 body 字段名不同（抓包原样）：
#   collect  -> {"note_id": "..."}   收藏单条
#   uncollect-> {"note_ids": "a,b"}  取消收藏（复数，逗号分隔批量）
#   like     -> {"note_oid": "..."}  点赞（是 note_oid 不是 note_id！）
#   dislike  -> {"note_oid": "..."}  取消点赞（返回 data.like_count 为取消后计数）


def collect_note(cookies: dict[str, str], note_id: str) -> dict:
    """收藏一条笔记（同步阻塞，异步侧用 asyncio.to_thread）。"""
    return _signed_post(cookies, constants.COLLECT_NOTE_URL, {"note_id": note_id})


def uncollect_notes(cookies: dict[str, str], note_ids: list[str]) -> dict:
    """批量取消收藏（同步阻塞）；note_ids 逗号拼接单请求，单批上限 UNCOLLECT_BATCH。"""
    return _signed_post(
        cookies, constants.UNCOLLECT_NOTE_URL, {"note_ids": ",".join(note_ids)}
    )


def like_note(cookies: dict[str, str], note_oid: str) -> dict:
    """点赞一条笔记（同步阻塞）；成功响应 data.new_like=true。"""
    return _signed_post(cookies, constants.LIKE_NOTE_URL, {"note_oid": note_oid})


def dislike_note(cookies: dict[str, str], note_oid: str) -> dict:
    """取消点赞一条笔记（同步阻塞）；成功响应 data.like_count 为取消后计数。"""
    return _signed_post(cookies, constants.DISLIKE_NOTE_URL, {"note_oid": note_oid})
