"""Bilibili 收藏夹接口响应 → 通用 content 行的解析。"""
import json
import re
from datetime import datetime

_SPACE_MID_RE = re.compile(r"space\.bilibili\.com/(\d+)")


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ts_iso(ts) -> str | None:
    """epoch 秒 → 本地 ISO 时间。"""
    ts = _as_int(ts)
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def extract_mid(url: str) -> str | None:
    """从 space 主页 / 收藏夹主页 URL 提取用户 id。"""
    m = _SPACE_MID_RE.search(url or "")
    return m.group(1) if m else None


def parse_media(media: dict) -> dict:
    """单个 media → contents 表字段（不含 platform / account_id，由写入方补）。"""
    upper = media.get("upper") or {}
    cnt = media.get("cnt_info") or {}
    bvid = media.get("bvid") or media.get("bv_id")
    return {
        "content_id": bvid or str(media.get("id") or ""),
        "title": media.get("title"),
        "description": media.get("intro") or None,
        "author_id": str(upper.get("mid") or "") or None,
        "author_name": upper.get("name"),
        "cover_url": media.get("cover"),
        "duration": _as_int(media.get("duration")),
        "statistics": json.dumps(
            {
                "play": _as_int(cnt.get("play")),
                "danmaku": _as_int(cnt.get("danmaku")),
                "reply": _as_int(cnt.get("reply")),
                "collect": _as_int(cnt.get("collect")),
                "thumb_up": _as_int(cnt.get("thumb_up")),
            },
            ensure_ascii=False,
        ),
        "raw_data": json.dumps(media, ensure_ascii=False),
        "collected_at": _ts_iso(media.get("fav_time")),
    }


def parse_resource_list(data: dict) -> dict:
    """fav/resource/list 的 data → {items, has_more, total, owner, favorite}。"""
    info = data.get("info") or {}
    upper = info.get("upper") or {}
    medias = data.get("medias") or []
    return {
        "items": [
            parse_media(m)
            for m in medias
            if m.get("bvid") or m.get("bv_id") or m.get("id")
        ],
        "has_more": bool(data.get("has_more")),
        "total": _as_int(info.get("media_count")) or 0,
        "owner": {
            "mid": str(upper.get("mid") or info.get("mid") or ""),
            "name": upper.get("name"),
            "avatar": upper.get("face"),  # B 站原字段 face，统一输出为 avatar
        },
        "favorite": {
            "media_id": str(info.get("id") or ""),
            "title": info.get("title"),
            "media_count": _as_int(info.get("media_count")),
        },
    }


def parse_folder_list(data: dict) -> dict:
    """fav/folder/created/list-all 的 data → {owner, folders}。

    该接口不含主人昵称/头像，owner.name/avatar 置空，由 resource/list 的 upper 补全。
    """
    folders = [
        {
            "media_id": str(f.get("id") or ""),
            "title": f.get("title"),
            "media_count": _as_int(f.get("media_count")),
            "cover": f.get("cover"),
            "intro": f.get("intro"),
        }
        for f in (data.get("list") or [])
        if f.get("id")
    ]
    owner_mid = next((str(f.get("mid")) for f in (data.get("list") or []) if f.get("mid")), "")
    return {"owner": {"mid": owner_mid, "name": None, "avatar": None}, "folders": folders}
