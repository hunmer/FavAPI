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
        # 原站链接（数字 id 无法独立成链，需作者 uniqueId）；图文以 /video/ 路径访问同样渲染
        "share_url": (
            f"https://www.tiktok.com/@{author.get('uniqueId')}/video/{item.get('id')}"
            if author.get("uniqueId") and item.get("id") else None
        ),
    }


def parse_item_list(data: dict) -> dict:
    """favorite / collect / post 列表响应 JSON → {items, cursor, has_more, total}。

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


def parse_following_list(data: dict) -> dict:
    """user/list（关注列表）响应 JSON → {followings, cursor, has_more, total}。

    条目结构对齐 follows 契约的统一 followings 行；cursor 取响应 minCursor
    （秒级时间戳 = 本页最旧一条的关注时间，作为下一页 maxCursor 入参）。
    """
    followings = []
    for entry in data.get("userList") or []:
        user = entry.get("user") or {}
        if not user.get("secUid"):
            continue
        stats = entry.get("stats") or {}
        followings.append({
            "sec_uid": user.get("secUid"),
            "uid": str(user.get("id") or ""),
            "unique_id": user.get("uniqueId"),
            "nickname": user.get("nickname"),
            "signature": user.get("signature"),
            "avatar_url": user.get("avatarLarger") or user.get("avatarMedium"),
            "follower_count": _as_int(stats.get("followerCount")),
            "aweme_count": _as_int(stats.get("videoCount")),
            "is_top": None,
        })
    return {
        "followings": followings,
        "cursor": _as_int(data.get("minCursor")),
        "has_more": bool(data.get("hasMore")),
        "total": _as_int(data.get("total")) or 0,
    }


_UNIVERSAL_DATA = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S)


def parse_item_detail_html(html: str) -> dict | None:
    """帖子详情页 HTML 内嵌的 __UNIVERSAL_DATA_FOR_REHYDRATION__ → itemStruct。

    webapp.video-detail 为服务端渲染的公开数据（访客可见）：视频含
    video.playAddr / bitrateInfo，图文含 imagePost.images。解析失败返回 None。
    注意：图文帖必须以 /video/{id} 路径访问页面才有该段（/photo/ 路径不渲染）。
    """
    match = _UNIVERSAL_DATA.search(html)
    if not match:
        return None
    try:
        scope = json.loads(match.group(1)).get("__DEFAULT_SCOPE__") or {}
        item = (((scope.get("webapp.video-detail") or {}).get("itemInfo") or {})
                .get("itemStruct")) or None
    except json.JSONDecodeError:
        return None
    return item if item and item.get("id") else None


def parse_download_links(item: dict) -> list[dict]:
    """itemStruct（帖子详情）→ 可下载直链列表（首项为推荐地址）。

    图文（imagePost.images 非空）：逐张原图直链（kind=image）+ 末尾附文案
    （kind=text，无 url，由调用方直接落盘 txt）+ 背景音乐（kind=audio，
    music.playUrl 直链，实测 audio/mp4 容器，文件名 music.m4a）。
    视频：bitrateInfo 各档按分辨率降序，同一 UrlList 内 v19-webapp-prime
    主机优先（v16 对部分出口 IP 返回 403，2026-09 实测）。
    """
    images = (item.get("imagePost") or {}).get("images") or []
    if images:
        links: list[dict] = []
        total = len(images)
        for i, img in enumerate(images, start=1):
            url_list = ((img.get("imageURL") or {}).get("urlList")) or []
            url = next((str(u) for u in url_list if str(u or "").startswith("http")), None)
            if not url:
                continue
            links.append({
                "url": url, "label": f"图片 {i}/{total}", "kind": "image", "ext": "jpeg",
                "width": _as_int(img.get("imageWidth")) or 0,
                "height": _as_int(img.get("imageHeight")) or 0,
            })
        desc = str(item.get("desc") or "").strip()
        if desc:
            links.append({"kind": "text", "text": desc, "label": "文案"})
        music_url = str((item.get("music") or {}).get("playUrl") or "")
        if music_url.startswith("http"):
            # playUrl 无后缀，实测 content-type=audio/mp4（AAC/MP4 容器，即 m4a）
            links.append({"url": music_url, "label": "音乐", "kind": "audio", "ext": "m4a"})
        return links

    video = item.get("video") or {}
    links = []
    seen: set[str] = set()
    gears = sorted(
        video.get("bitrateInfo") or [],
        key=lambda b: _as_int((b.get("PlayAddr") or {}).get("Height")) or 0,
        reverse=True,
    )
    for br in gears:
        play_addr = br.get("PlayAddr") or {}
        url_list = [str(u) for u in play_addr.get("UrlList") or []
                    if str(u or "").startswith("http")]
        url = next((u for u in url_list if "v19-webapp-prime" in u),
                   url_list[0] if url_list else None)
        if not url or url in seen:
            continue
        seen.add(url)
        height = _as_int(play_addr.get("Height")) or 0
        label = f"{height}p" if height else str(br.get("GearName") or "视频")
        if str(br.get("CodecType") or "") in ("h265", "hevc"):
            label += " H.265"
        links.append({
            "url": url, "label": label, "ext": "mp4", "kind": "video",
            "width": _as_int(play_addr.get("Width")) or 0, "height": height,
            "size": _as_int(play_addr.get("DataSize")) or 0,
        })
    return links


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


def parse_play_info(item: dict) -> dict:
    """itemStruct（帖子详情 SSR）→ 前端播放器信息（follows PlayerModal 统一结构）。

    视频：bitrateInfo 各档 + video.playAddr（去重，v19 主机优先）；
    图文（imagePost.images 非空）：逐张原图直链；音乐 playUrl 附带。
    duration 单位为秒（TikTok 原生秒，勿混入抖音毫秒语义）。
    """
    stats = item.get("stats") or {}
    author = item.get("author") or {}
    info = {
        "aweme_id": str(item.get("id") or ""),
        "desc": (item.get("desc") or "").strip(),
        "create_time": _as_int(item.get("createTime")),
        "aweme_type": 0,
        "duration": _as_int((item.get("video") or {}).get("duration")),
        "statistics": {
            "digg_count": _as_int(stats.get("diggCount")),
            "comment_count": _as_int(stats.get("commentCount")),
            "share_count": _as_int(stats.get("shareCount")),
            "collect_count": _as_int(stats.get("collectCount")),
            "play_count": _as_int(stats.get("playCount")),
        },
        "author": {
            "nickname": author.get("nickname"),
            "sec_uid": author.get("secUid"),
        },
        "video_urls": [],
        "images": [],
    }

    images = (item.get("imagePost") or {}).get("images") or []
    if not images:
        video = item.get("video") or {}
        seen: set[str] = set()

        def _push(url_list) -> None:
            urls = [str(u) for u in url_list or [] if str(u or "").startswith("http")]
            url = next((u for u in urls if "v19-webapp-prime" in u),
                       urls[0] if urls else None)
            if url and url not in seen:
                seen.add(url)
                info["video_urls"].append(url)

        for br in video.get("bitrateInfo") or []:
            _push((br.get("PlayAddr") or {}).get("UrlList"))
        _push([video.get("playAddr")])
    for img in images:
        url_list = ((img.get("imageURL") or {}).get("urlList")) or []
        url = next((str(u) for u in url_list if str(u or "").startswith("http")), None)
        if url:
            info["images"].append({
                "url": url,
                "width": _as_int(img.get("imageWidth")) or 0,
                "height": _as_int(img.get("imageHeight")) or 0,
            })
    music_url = str((item.get("music") or {}).get("playUrl") or "")
    info["music_url"] = music_url if music_url.startswith("http") else None
    # 原站链接（数字 item_id 无法独立成链，需作者 uniqueId）：图文走 /photo/，视频走 /video/
    handle = str(author.get("uniqueId") or "").strip()
    info["share_url"] = (
        f"https://www.tiktok.com/@{handle}/{'photo' if images else 'video'}/{info['aweme_id']}"
        if handle else None
    )
    if not info["video_urls"] and not info["images"]:
        raise RuntimeError("详情响应无可用播放地址（作品可能已删除或设为私密）")
    return info
