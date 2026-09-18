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


def _manifest_links(manifest, label_prefix: str, links: list, seen: set) -> None:
    """manifest（dict 或 JSON 串）→ representation 直链追加进 links（按 URL 去重）。"""
    if isinstance(manifest, str):
        try:
            manifest = json.loads(manifest)
        except ValueError:
            return
    for adaptation in (manifest or {}).get("adaptationSet") or []:
        for rep in adaptation.get("representation") or []:
            if rep.get("hidden"):
                continue
            quality = str(rep.get("qualityLabel") or "").strip()
            label = f"{label_prefix} {quality}".strip()
            width = _as_int(rep.get("width")) or 0
            height = _as_int(rep.get("height")) or 0
            if height:
                label = f"{label} {height}p"
            for url in [rep.get("url")] + (rep.get("backupUrl") or []):
                url = str(url or "")
                if not url.startswith("http") or url in seen:
                    continue
                seen.add(url)
                links.append({
                    "url": url, "label": label, "ext": "mp4", "kind": "video",
                    "width": width, "height": height,
                })


def parse_video_detail(data: dict) -> dict:
    """graphql visionVideoDetail 响应 → 详情摘要（status != 1 / 无 photo 时由调用方先抛错）。

    返回 {photo_id, caption, duration, timestamp, author_id, author_name}；
    直链解析见 parse_download_links。
    """
    detail = (data.get("data") or {}).get("visionVideoDetail") or {}
    photo = detail.get("photo") or {}
    author = detail.get("author") or {}
    return {
        "photo_id": str(photo.get("id") or ""),
        "caption": (photo.get("caption") or "").strip(),
        "duration": _as_int(photo.get("duration")),
        "timestamp": _as_int(photo.get("timestamp")),
        "author_id": str(author.get("id") or ""),
        "author_name": author.get("name"),
    }


def parse_download_links(data: dict) -> list[dict]:
    """graphql visionVideoDetail 响应 → 可下载直链列表（首项为推荐地址）。

    H.264 直链（photoUrl）兼容性最好放首位，随后 manifest 各档（含 backupUrl）；
    H.265（photoH265Url / manifestH265）码率通常更高但部分播放器不支持，置于末尾。
    """
    photo = ((data.get("data") or {}).get("visionVideoDetail") or {}).get("photo") or {}
    if not photo.get("id"):
        return []
    links: list[dict] = []
    seen: set[str] = set()

    def _push(url, label: str) -> None:
        url = str(url or "")
        if not url.startswith("http") or url in seen:
            return
        seen.add(url)
        links.append({"url": url, "label": label, "ext": "mp4", "kind": "video"})

    _push(photo.get("photoUrl"), "H.264 直链")
    _manifest_links(photo.get("manifest"), "H.264", links, seen)
    _push(photo.get("photoH265Url"), "H.265 直链（高画质）")
    _manifest_links(photo.get("manifestH265"), "H.265", links, seen)
    return links
