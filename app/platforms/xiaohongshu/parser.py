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


def parse_following_page(data: dict, page_size: int) -> dict:
    """im/web/users/following/all 响应 → {items, has_more}，items 为 follows 体系统一关注人结构。

    条目仅有 user_id / nick_name / avatar（IM 通道精简结构），粉丝数、作品数、
    签名、特别关注标记接口均不下发，置 None / 空由前端兜底；接口无 has_more
    字段，满页（== page_size）即视为可能有下一页，末页返回空列表。
    """
    entries = (data.get("data") or {}).get("follow_user_d_t_o_list") or []
    followings = []
    for u in entries:
        user_id = str(u.get("user_id") or "")
        if not user_id:
            continue
        followings.append({
            "sec_uid": user_id,
            "uid": user_id,
            "unique_id": "",
            "nickname": u.get("nick_name") or "",
            "signature": "",
            "avatar_url": u.get("avatar") or "",
            "follower_count": None,
            "aweme_count": None,
            "is_top": False,
        })
    return {"items": followings, "has_more": len(followings) >= page_size}


def parse_download_links(data: dict) -> list[dict]:
    """feed 详情响应 → 可下载直链列表（首项为推荐地址）。

    视频笔记：video.media.stream 按编解码分组，分组键随构建混淆（实测 EF4/EF5），
    按 format=="mp4" 取完整可下载文件（fmp4/m4s 为无音轨 DASH 分段，不采用），
    多档按高度降序（首项最高清）；图文笔记：逐张原图直链 + 末尾附文案
    （kind=text，无 url，由调用方直接落盘 txt）。
    """
    items = (data.get("data") or {}).get("items") or []
    note = next((it.get("note_card") or {} for it in items if it.get("note_card")), {})
    if not note.get("note_id"):
        return []
    if note.get("type") == "video" and note.get("video"):
        return _parse_video_links(note["video"])
    return _parse_image_links(note)


def _parse_video_links(video: dict) -> list[dict]:
    stream = ((video.get("media") or {}).get("stream")) or {}
    links: list[dict] = []
    for streams in stream.values():
        if not isinstance(streams, list):
            continue
        for s in streams:
            if not isinstance(s, dict):
                continue
            url = str(s.get("master_url") or "")
            if s.get("format") != "mp4" or not url.startswith("http"):
                continue
            height = _as_int(s.get("height")) or 0
            label = f"视频 {height}p" if height else "视频"
            quality = str(s.get("quality_type") or "").strip()
            if quality:
                label += f"（{quality}）"
            links.append({
                "url": url, "label": label, "ext": "mp4", "kind": "video",
                "width": _as_int(s.get("width")) or 0, "height": height,
                "size": _as_int(s.get("size")) or 0,
            })
    links.sort(key=lambda l: l["height"], reverse=True)
    seen: set[str] = set()
    return [l for l in links if not (l["url"] in seen or seen.add(l["url"]))]


def _parse_image_links(note: dict) -> list[dict]:
    images = note.get("image_list") or []
    links: list[dict] = []
    for i, img in enumerate(images, start=1):
        url = str(img.get("url_default") or img.get("url") or "")
        if not url.startswith("http"):
            continue
        links.append({
            "url": url, "label": f"图片 {i}/{len(images)}", "kind": "image",
            "ext": "jpg",  # CDN 路径无扩展名；请求 image_formats 已含 jpg
            "width": _as_int(img.get("width")) or 0,
            "height": _as_int(img.get("height")) or 0,
        })
    text = f"{note.get('title') or ''}\n{note.get('desc') or ''}".strip()
    if text:
        links.append({"kind": "text", "text": text, "label": "文案"})
    return links
