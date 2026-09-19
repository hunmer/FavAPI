"""Instagram API 响应解析：REST v1 与 GraphQL 响应 → 统一结构 / 通用 content 行。

媒体对象（pk/code/media_type/caption/image_versions2/video_versions/carousel_media/
taken_at/user）在三个接口同构：投稿列表 GraphQL 的 edges[].node、收藏列表的
items[].media、详情接口的 items[0]，content 行解析共用 _media_content_row。
"""
import json
import logging
from datetime import datetime

from . import constants

logger = logging.getLogger("favapi.instagram.parser")


def _taken_at_iso(taken_at) -> str | None:
    if not taken_at:
        return None
    try:
        return datetime.fromtimestamp(int(taken_at)).astimezone().isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def _cover_url(media: dict) -> str | None:
    """封面：image_versions2 候选中面积最大者（视频与单图通用）。"""
    candidates = ((media.get("image_versions2") or {}).get("candidates") or [])
    best = max(
        (c for c in candidates if str(c.get("url") or "").startswith("http")),
        key=lambda c: (c.get("width") or 0) * (c.get("height") or 0),
        default=None,
    )
    return best.get("url") if best else None


def _media_content_row(media: dict) -> dict | None:
    """单个媒体对象 → 通用 content 行（pk 缺失返回 None）。

    collected_at 语义 = 发布时间 taken_at（follows 路由下发为 published_at；
    Instagram 收藏接口不返回加入收藏时间，与 Threads 同策略兜底）。
    """
    pk = media.get("pk")
    if not pk:
        return None
    caption = (media.get("caption") or {}).get("text") or ""
    user = media.get("user") or {}
    return {
        "content_id": str(pk),
        "title": caption,
        "description": caption,
        "author_id": str(user.get("pk") or user.get("id") or ""),
        "author_name": user.get("username"),
        "cover_url": _cover_url(media),
        "collected_at": _taken_at_iso(media.get("taken_at")),
        "statistics": json.dumps({
            "like_count": media.get("like_count"),
            "comment_count": media.get("comment_count"),
            "play_count": media.get("play_count"),
        }, ensure_ascii=False),
        "raw_data": json.dumps(media, ensure_ascii=False),
    }


def parse_saved_list(data: dict) -> dict:
    """解析收藏列表（REST v1 feed/saved/posts）→ {items, cursor, has_more}。

    items 为 [{media: {...}}] 嵌套结构；翻页游标 next_max_id（首页后必非空）。
    """
    items = []
    for entry in data.get("items") or []:
        row = _media_content_row(entry.get("media") or {})
        if row:
            items.append(row)
    return {
        "items": items,
        "cursor": data.get("next_max_id") or "",
        "has_more": bool(data.get("more_available")),
    }


def parse_following_list(data: dict) -> dict:
    """解析关注列表（REST v1 friendships/{uid}/following）→ {followings, cursor, has_more}。

    该接口不下发粉丝数与帖子数（置 None，前端兜底展示）；
    max_id 为纯偏移量（首页 "12"、次页 "24"），原样回传翻页。
    """
    followings = []
    for u in data.get("users") or []:
        if not u.get("pk"):
            continue
        followings.append({
            "pk": str(u.get("pk")),
            "username": u.get("username"),
            "full_name": u.get("full_name"),
            "avatar_url": u.get("profile_pic_url"),
            "follower_count": None,
            "is_verified": bool(u.get("is_verified")),
            "is_private": bool(u.get("is_private")),
        })
    return {
        "followings": followings,
        "cursor": data.get("next_max_id") or "",
        "has_more": bool(data.get("has_more")),
    }


def parse_user_posts(data: dict) -> dict:
    """解析博主主页作品（GraphQL PolarisProfilePostsTabContentQuery_connection）。

    连接在根字段 xdt_api__v1__feed__user_timeline_graphql_connection 下；
    end_cursor 形如 "{media_pk}_{user_pk}"，has_more = page_info.has_next_page。
    """
    conn = ((data.get("data") or {}).get(constants.USER_POSTS_ROOT_FIELD)) or {}
    items = []
    for edge in conn.get("edges") or []:
        row = _media_content_row(edge.get("node") or {})
        if row:
            items.append(row)
    page_info = conn.get("page_info") or {}
    return {
        "items": items,
        "cursor": page_info.get("end_cursor") or "",
        "has_more": bool(page_info.get("has_next_page")),
    }


def parse_media_info(data: dict) -> dict:
    """解析作品详情（REST v1 media/{pk}/info 的完整响应）→ 通用 content 行。"""
    items = data.get("items") or []
    return _media_content_row(items[0]) if items else None


def parse_play_info(media: dict) -> dict:
    """作品详情媒体对象 → PlayerModal 播放信息统一结构。

    duration 单位秒（video_duration）；statistics 附 play_count；
    视频 video_versions 取 type=101 的 mp4（102/103 为同链分片变体），
    图文 carousel_media 逐张（单图无该字段，用 media 本体）。
    """
    user = media.get("user") or {}
    videos = [
        str(v.get("url") or "") for v in media.get("video_versions") or []
        if v.get("type") == 101 and str(v.get("url") or "").startswith("http")
    ]
    images = []
    for item in media.get("carousel_media") or [media]:
        url = _cover_url(item)
        if url:
            images.append({"url": url})
    duration = media.get("video_duration")
    return {
        "aweme_id": str(media.get("pk") or ""),
        "desc": (media.get("caption") or {}).get("text"),
        "create_time": media.get("taken_at"),
        "aweme_type": 0,
        "duration": round(duration) if duration else None,  # 秒（前端 fmtMs 按数量级归一）
        "statistics": {
            "digg_count": media.get("like_count"),
            "comment_count": media.get("comment_count"),
            "play_count": media.get("play_count"),
        },
        "author": {"nickname": user.get("username"),
                   "sec_uid": str(user.get("pk") or user.get("id") or "")},
        # CDN 直链（scontent-*.cdninstagram.com）仅 UA 即可访问，媒体代理按域附加 UA
        "video_urls": videos,
        "images": images,
    }
