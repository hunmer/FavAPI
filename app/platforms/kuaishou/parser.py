"""快手 collect/list / feed/liked 响应 → 通用 content 行的解析。"""
import json
from datetime import datetime

from .constants import PCURSOR_NO_MORE


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_feed(feed: dict) -> dict:
    """单个 feeds[] 元素 → contents 表字段（不含 platform / account_id，由写入方补）。

    收藏/点赞列表同构：视频在 photo，作者在 author；列表接口不提供收藏时间，
    用作品发布时间 photo.timestamp（毫秒 epoch）兜底 collected_at。
    """
    photo = feed.get("photo") or {}
    author = feed.get("author") or {}
    content_id = str(photo.get("id") or "")
    if not content_id:
        return {}

    caption = (photo.get("caption") or "").strip()
    title = caption.splitlines()[0][:120] if caption else None

    collected_at = None
    ts = _as_int(photo.get("timestamp"))
    if ts:
        try:  # 毫秒时间戳
            collected_at = datetime.fromtimestamp(ts / 1000).astimezone().isoformat(
                timespec="seconds")
        except (OSError, OverflowError, ValueError):
            collected_at = None

    statistics = {
        "like_count": _as_int(photo.get("likeCount")),
        "view_count": _as_int(photo.get("viewCount")),
        "comment_count": _as_int((photo.get("comment") or {}).get("commentCount")),
    }

    return {
        "content_id": content_id,
        "title": title,
        "description": caption or None,
        "author_id": str(author.get("id") or "") or None,
        "author_name": author.get("name"),
        "cover_url": photo.get("coverUrl") or photo.get("webpCoverUrl"),
        "duration": _as_int(photo.get("duration")),  # 毫秒，与抖音 parser 语义一致
        "statistics": json.dumps(statistics, ensure_ascii=False),
        "raw_data": json.dumps(feed, ensure_ascii=False),
        "collected_at": collected_at,
    }


def parse_feeds_page(data: dict) -> dict:
    """collect/list / feed/liked 响应 → {items, pcursor, has_more}。

    翻页：首页 pcursor 传空串，后续传上页返回值；末页 pcursor="no_more"。
    """
    feeds = data.get("feeds") or []
    pcursor = str(data.get("pcursor") or "")
    has_more = bool(pcursor) and pcursor != PCURSOR_NO_MORE
    return {
        "items": [item for f in feeds if (item := parse_feed(f))],
        "pcursor": pcursor,
        "has_more": has_more,
    }


def parse_profile(data: dict) -> dict:
    """profile/get 响应 → 用户信息摘要（result != 1 时由调用方先抛错）。"""
    return {
        "eid": str(data.get("eid") or ""),
        "user_id": str(data.get("userId") or ""),
        "user_name": data.get("userName"),
        "sex": data.get("sex"),
        "fans": _as_int(data.get("fans")),
        "follows": _as_int(data.get("follows")),
        "avatar": data.get("userHead"),
    }
