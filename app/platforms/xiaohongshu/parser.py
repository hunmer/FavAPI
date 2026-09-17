"""小红书 collect/page 响应 → 通用 content 行的解析。"""
import json
import re
from datetime import datetime

# 个人主页 URL：xiaohongshu.com/user/profile/{24 位十六进制用户 id}
_PROFILE_USER_RE = re.compile(r"xiaohongshu\.com/user/profile/([0-9a-fA-F]{16,32})")
_USER_ID_RE = re.compile(r"[0-9a-fA-F]{16,32}")


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_user_id(url: str) -> str | None:
    """从个人主页 URL 提取用户 id。"""
    m = _PROFILE_USER_RE.search(url or "")
    return m.group(1) if m else None


def is_user_id(value: str) -> bool:
    return bool(_USER_ID_RE.fullmatch(value or ""))


def _cover_url(cover: dict) -> str | None:
    """cover.url_default / url_pre，缺失时回退 info_list 的 WB_DFT。"""
    if not cover:
        return None
    url = cover.get("url_default") or cover.get("url_pre")
    if url:
        return url
    infos = cover.get("info_list") or []
    for info in infos:
        if info.get("image_scene") == "WB_DFT" and info.get("url"):
            return info["url"]
    return infos[0].get("url") if infos else None


def _ts_iso(value) -> str | None:
    """毫秒时间戳 → 本地 ISO；无效返回 None。"""
    try:
        ts = int(value)
        if ts > 10**12:  # 毫秒
            ts //= 1000
        return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _id_ts_iso(value) -> str | None:
    """id 前 8 位十六进制为对象创建时间 Unix 秒（小红书 note_id 为 Mongo ObjectId 格式）。

    列表接口（collect/like page）不含任何时间字段，用 note_id 时间戳兜底发布时间
    （2026-09 实测多条笔记与标题语境吻合）。
    """
    try:
        return _ts_iso(int(str(value)[:8], 16) * 1000)
    except (TypeError, ValueError):
        return None


def parse_note(note: dict) -> dict:
    """单个 note → contents 表字段（不含 platform / account_id，由写入方补）。"""
    user = note.get("user") or {}
    interact = note.get("interact_info") or {}
    return {
        "content_id": str(note.get("note_id") or ""),
        "title": note.get("display_title") or None,
        "description": None,
        "author_id": str(user.get("user_id") or "") or None,
        "author_name": user.get("nickname"),
        "cover_url": _cover_url(note.get("cover")),
        "duration": None,
        "statistics": json.dumps(
            {"liked_count": _as_int(interact.get("liked_count"))}, ensure_ascii=False
        ),
        "raw_data": json.dumps(note, ensure_ascii=False),
        # 收藏列表接口不含收藏时间，兜底链：发布时间字段 → note_id 时间戳（均为发布时间）
        "collected_at": (
            _ts_iso(note.get("time") or note.get("last_update_time"))
            or _id_ts_iso(note.get("note_id"))
        ),
    }


def parse_collect_page(data: dict) -> dict:
    """collect/page 响应 JSON → {items, cursor, has_more, total}。cursor 为不透明字符串。"""
    payload = (data.get("data") if isinstance(data, dict) else None) or {}
    notes = payload.get("notes") or []
    return {
        "items": [parse_note(n) for n in notes if n.get("note_id")],
        "cursor": payload.get("cursor"),
        "has_more": bool(payload.get("has_more")),
        "total": 0,  # 接口不返回总数
    }
