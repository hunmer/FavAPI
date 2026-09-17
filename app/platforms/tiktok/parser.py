"""TikTok item_list 响应 / 个人主页 HTML → 通用 content 行与用户信息的解析。"""
import json
import re
from datetime import datetime


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _epoch_to_iso(value) -> str | None:
    """epoch 秒 → 本地时区 ISO 字符串；无效返回 None。"""
    ts = _as_int(value)
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def parse_item(item: dict) -> dict:
    """itemList 单条 → contents 表字段（不含 platform / account_id，由写入方补）。"""
    author = item.get("author") or {}
    video = item.get("video") or {}
    stats = item.get("stats") or {}

    desc = (item.get("desc") or "").strip()
    title = desc.splitlines()[0][:120] if desc else None

    statistics = {
        k: _as_int(stats.get(k))
        for k in ("diggCount", "commentCount", "shareCount", "collectCount", "playCount")
    }

    # 收藏时间：collect 列表可能带加入时间字段，缺失时用发布时间兜底
    collected_at = None
    for key in ("collectAt", "collectedAt", "createTime"):
        collected_at = _epoch_to_iso(item.get(key))
        if collected_at:
            break

    return {
        "content_id": str(item.get("id") or ""),
        "title": title,
        "description": desc or None,
        "author_id": str(author.get("uniqueId") or author.get("id") or "") or None,
        "author_name": author.get("nickname"),
        "cover_url": (video.get("cover") or video.get("originCover")
                      or video.get("dynamicCover")),
        "duration": _as_int(video.get("duration")),
        "statistics": json.dumps(statistics, ensure_ascii=False),
        "raw_data": json.dumps(item, ensure_ascii=False),
        "collected_at": collected_at,
    }


def parse_item_list(data: dict) -> dict:
    """favorite / collect 列表响应 JSON → {items, cursor, has_more, total}。

    cursor 为毫秒时间戳（首页传 0），作为下一页入参原样回传。
    """
    raw_items = data.get("itemList") or []
    items = [parse_item(it) for it in raw_items if it.get("id")]
    return {
        "items": items,
        "cursor": _as_int(data.get("cursor")),
        "has_more": bool(data.get("hasMore")),
        "total": _as_int(data.get("total")) or 0,
    }


_UNIVERSAL_DATA = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S)


def parse_user_detail_html(html: str) -> dict | None:
    """个人主页 HTML 内嵌的 __UNIVERSAL_DATA_FOR_REHYDRATION__ → 用户信息。

    webapp.user-detail 为服务端渲染的公开数据（访客可见），字段：
    user{id/uniqueId/nickname/secUid/avatarLarger} + stats{followerCount...}。
    解析失败返回 None。
    """
    match = _UNIVERSAL_DATA.search(html)
    if not match:
        return None
    try:
        scope = json.loads(match.group(1)).get("__DEFAULT_SCOPE__") or {}
        user_info = (scope.get("webapp.user-detail") or {}).get("userInfo") or {}
    except json.JSONDecodeError:
        return None
    user = user_info.get("user") or {}
    if not user.get("id"):
        return None
    stats = user_info.get("stats") or {}
    return {
        "user_id": str(user.get("id") or ""),
        "unique_id": user.get("uniqueId"),
        "sec_uid": user.get("secUid"),
        "nickname": user.get("nickname"),
        "avatar": user.get("avatarLarger"),
        "signature": user.get("signature"),
        "stats": {
            "followerCount": _as_int(stats.get("followerCount")),
            "followingCount": _as_int(stats.get("followingCount")),
            "heartCount": _as_int(stats.get("heartCount")),
            "videoCount": _as_int(stats.get("videoCount")),
        },
    }
