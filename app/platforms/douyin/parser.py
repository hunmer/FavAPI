"""抖音 listcollection 响应 → 通用 content 行的解析。"""
import json
import re
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


def _parse_aweme_page(data: dict, cursor_key: str = "max_cursor") -> dict:
    """aweme_list + 游标型列表响应的通用解析（favorite / history 同构）。"""
    aweme_list = data.get("aweme_list") or []
    items = [parse_aweme(a) for a in aweme_list if a.get("aweme_id")]
    return {
        "items": items,
        "cursor": _as_int(data.get(cursor_key)),
        "has_more": bool(data.get("has_more")),
        "total": _as_int(data.get("total")) or 0,
    }


def parse_like_list(data: dict) -> dict:
    """喜欢(点赞)列表 /aweme/v1/web/aweme/favorite/ 响应 → {items, cursor, has_more, total}。"""
    return _parse_aweme_page(data)


def parse_download_links(data: dict) -> list[dict]:
    """aweme/detail 响应 → 可下载直链列表（首项为推荐地址）。

    视频：依次收 play_addr（默认画质）与 bit_rate 各档（多码率），按 URL 去重；
    老版地址带 playwm（带水印标记），统一替换为 play 以取无水源。
    图文（aweme_type=68 / images 非空）：逐张原图链接（kind=image）+ 末尾附文案
    （kind=text，无 url，由调用方直接落盘 txt）+ 背景音乐（kind=audio，
    music.play_url 直链，文件名 music.{ext}）。
    """
    aweme = data.get("aweme_detail") or {}
    if not aweme.get("aweme_id"):
        return []
    images = aweme.get("images") or []
    if images or _as_int(aweme.get("aweme_type")) == 68:
        return _parse_note_links(aweme, images)

    video = aweme.get("video") or {}
    links: list[dict] = []
    seen: set[str] = set()

    def _push(play_addr: dict, label: str) -> None:
        width = _as_int((play_addr or {}).get("width")) or 0
        height = _as_int((play_addr or {}).get("height")) or 0
        size = _as_int((play_addr or {}).get("data_size")) or 0
        if height:
            label = f"{label} {height}p"
        for raw in (play_addr or {}).get("url_list") or []:
            url = str(raw or "").replace("playwm", "play")
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            links.append({
                "url": url, "label": label, "ext": "mp4", "kind": "video",
                "width": width, "height": height, "size": size,
            })

    _push(video.get("play_addr"), "默认画质")
    for br in video.get("bit_rate") or []:
        gear = str(br.get("gear_name") or "").rstrip("_0") or "多码率"
        _push(br.get("play_addr"), gear)
    return links


def _parse_note_links(aweme: dict, images: list) -> list[dict]:
    """图文 note → 原图直链列表 + 文案项。"""
    links: list[dict] = []
    total = len(images)
    for i, img in enumerate(images, start=1):
        urls = (img.get("download_url_list") or []) + (img.get("url_list") or [])
        url = next((str(u) for u in urls if str(u or "").startswith("http")), None)
        if not url:
            continue
        m = re.search(r"\.(jpe?g|png|webp|heic)(?:[?~]|$)", url, re.I)
        links.append({
            "url": url, "label": f"图片 {i}/{total}", "kind": "image",
            "ext": m.group(1).lower() if m else "jpeg",
            "width": _as_int(img.get("width")) or 0,
            "height": _as_int(img.get("height")) or 0,
        })
    desc = str(aweme.get("desc") or "").strip()
    if desc:
        links.append({"kind": "text", "text": desc, "label": "文案"})
    music_urls = (((aweme.get("music") or {}).get("play_url") or {}).get("url_list")) or []
    music_url = next((str(u) for u in music_urls if str(u or "").startswith("http")), None)
    if music_url:
        m = re.search(r"\.(mp3|m4a|aac|wav|flac)(?:\?|$)", music_url, re.I)
        links.append({
            "url": music_url, "label": "音乐", "kind": "audio",
            "ext": m.group(1).lower() if m else "mp3",
        })
    return links


def parse_history(data: dict) -> dict:
    """观看历史 /aweme/v1/web/history/read/ 响应 → {items, cursor, has_more, total}。

    与 favorite 同构（aweme_list + max_cursor 游标）；接口属强校验，需活跃登录态。
    """
    return _parse_aweme_page(data)


def parse_watchlater(data: dict) -> dict:
    """稍后再看 /aweme/v1/web/watchlater/list/ 响应 → {items, cursor, has_more, total}。

    顶层条目字段为 items（2026-09 实测：status_code/items/offset/has_more/list_num/
    invalid_item_ids）；分页用 offset 偏移量而非游标，cursor 输出下一页 offset。
    """
    raw_items = data.get("items") or []
    items = [parse_aweme(it) for it in raw_items if it.get("aweme_id")]
    offset = _as_int(data.get("offset")) or 0
    return {
        "items": items,
        "cursor": offset + len(raw_items),
        "has_more": bool(data.get("has_more")),
        "total": _as_int(data.get("list_num")) or 0,
    }
