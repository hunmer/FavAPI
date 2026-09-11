"""抖音 listcollection 响应 → 通用 content 行的解析。"""
import json
from datetime import datetime


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_aweme(aweme: dict) -> dict:
    """单个 aweme → contents 表字段（不含 platform / account_id，由写入方补）。"""
    author = aweme.get("author") or {}
    video = aweme.get("video") or {}

    cover_url = None
    for key in ("cover", "origin_cover", "ai_dynamic_cover", "dynamic_cover"):
        urls = ((video.get(key) or {}).get("url_list") or [])
        if urls:
            cover_url = urls[0]
            break

    desc = (aweme.get("desc") or "").strip()
    title = desc.splitlines()[0][:120] if desc else None

    stats = aweme.get("statistics") or {}
    statistics = {
        k: _as_int(stats.get(k))
        for k in ("digg_count", "comment_count", "share_count", "collect_count", "play_count")
    }

    # 收藏时间：不同版本接口字段名不同，逐个尝试（epoch 秒 → ISO）。
    # listcollection 当前响应通常不提供收藏时间，使用作品发布时间兜底，
    # 确保收藏记录的 collected_at 可用于展示和排序。
    collected_at = None
    for key in ("collect_time", "collected_at", "collect_date", "create_time"):
        ts = _as_int(aweme.get(key))
        if ts:
            try:
                collected_at = datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
            except (OSError, OverflowError, ValueError):
                collected_at = str(aweme.get(key))
            break

    return {
        "content_id": str(aweme.get("aweme_id") or ""),
        "title": title,
        "description": desc or None,
        "author_id": str(author.get("uid") or author.get("sec_uid") or "") or None,
        "author_name": author.get("nickname"),
        "cover_url": cover_url,
        "duration": _as_int(video.get("duration")),
        "statistics": json.dumps(statistics, ensure_ascii=False),
        "raw_data": json.dumps(aweme, ensure_ascii=False),
        "collected_at": collected_at,
    }


def parse_listcollection(data: dict) -> dict:
    """listcollection 响应 JSON → {items, cursor, has_more, total}。"""
    aweme_list = data.get("aweme_list") or []
    items = [parse_aweme(a) for a in aweme_list if a.get("aweme_id")]
    return {
        "items": items,
        "cursor": _as_int(data.get("cursor")),
        "has_more": bool(data.get("has_more")),
        "total": _as_int(data.get("total")) or 0,
    }
