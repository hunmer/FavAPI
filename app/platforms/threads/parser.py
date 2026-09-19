"""Threads 收藏（saved_media）响应解析：浏览器拦截响应 / API 直连响应 / HTML 预取数据共用。"""
import json
import logging
from datetime import datetime

logger = logging.getLogger("favapi.threads.parser")


def parse_saved_media(data: dict) -> dict:
    """解析 saved_media GraphQL 响应。

    输入为完整响应 {"data": {"xdt_text_app_viewer": {"saved_media": ...}}}；
    输出 {items, cursor, has_more}，items 为通用 content 行
    （字段与原声明式平台保持一致：pk/caption/user/image_versions2）。
    """
    viewer = ((data.get("data") or {}).get("xdt_text_app_viewer") or {})
    media = viewer.get("saved_media") or {}
    items = []
    for edge in media.get("edges") or []:
        node = edge.get("node") or {}
        for entry in node.get("thread_items") or []:
            post = (entry or {}).get("post") or {}
            pk = post.get("pk")
            if not pk:
                continue
            caption = (post.get("caption") or {}).get("text") or ""
            user = post.get("user") or {}
            candidates = ((post.get("image_versions2") or {}).get("candidates") or [])
            # Threads 不提供真实加入收藏时间，兜底用帖子发布时间（与抖音 parser 同策略）
            taken_at = post.get("taken_at")
            collected_at = None
            if taken_at:
                try:
                    collected_at = datetime.fromtimestamp(int(taken_at)).astimezone().isoformat(
                        timespec="seconds")
                except (OSError, OverflowError, ValueError):
                    collected_at = None
            items.append({
                "content_id": str(pk),
                "title": caption,
                "description": caption,
                "author_id": str(user.get("id") or ""),
                "author_name": user.get("username"),
                "cover_url": candidates[0].get("url") if candidates else None,
                "collected_at": collected_at,
                "raw_data": json.dumps(post, ensure_ascii=False),
            })
    page_info = media.get("page_info") or {}
    return {
        "items": items,
        "cursor": page_info.get("end_cursor") or "",
        "has_more": bool(page_info.get("has_next_page")),
    }


def parse_following_list(data: dict) -> dict:
    """解析关注列表（BarcelonaFriendshipsFollowingTabQuery）。

    输入为完整响应，连接在 data.user.following（edges[].node / page_info）；
    输出 {followings, cursor, has_more}。该查询不下发简介与帖子数（置 None，
    前端兜底展示），关注总数也不返回（接口层按已拉条数计 total）。
    """
    following = (((data.get("data") or {}).get("user") or {}).get("following")) or {}
    followings = []
    for edge in following.get("edges") or []:
        u = edge.get("node") or {}
        if not u.get("pk"):
            continue
        followings.append({
            "pk": str(u.get("pk")),
            "username": u.get("username"),
            "full_name": u.get("full_name"),
            "avatar_url": u.get("profile_pic_url"),
            "follower_count": u.get("follower_count"),
            "is_verified": bool(u.get("is_verified")),
            "is_private": bool(u.get("text_post_app_is_private")),
        })
    page_info = following.get("page_info") or {}
    return {
        "followings": followings,
        "cursor": page_info.get("end_cursor") or "",
        "has_more": bool(page_info.get("has_next_page")),
    }


def parse_user_posts(data: dict) -> dict:
    """解析博主主页作品（BarcelonaProfileThreadsTabDirectQuery）→ 通用 content 行。

    连接在根字段别名 data.mediaData 下；一个 edge 是一条主帖时间线
    （thread_items[0].post 为主帖，自回复不单列，与 profile 页展示一致）；
    collected_at 语义 = 发布时间 taken_at（follows 路由直接下发为 published_at）。
    """
    conn = ((data.get("data") or {}).get("mediaData")) or {}
    items = []
    for edge in conn.get("edges") or []:
        entries = (edge.get("node") or {}).get("thread_items") or []
        post = ((entries[0] or {}) if entries else {}).get("post") or {}
        row = _post_content_row(post)
        if row:
            items.append(row)
    page_info = conn.get("page_info") or {}
    return {
        "items": items,
        "cursor": page_info.get("end_cursor") or "",
        "has_more": bool(page_info.get("has_next_page")),
    }


def _post_content_row(post: dict) -> dict | None:
    """单个帖子 → 通用 content 行（pk 缺失返回 None）。"""
    pk = post.get("pk")
    if not pk:
        return None
    caption = (post.get("caption") or {}).get("text") or ""
    user = post.get("user") or {}
    candidates = ((post.get("image_versions2") or {}).get("candidates") or [])
    taken_at = post.get("taken_at")
    collected_at = None
    if taken_at:
        try:
            collected_at = datetime.fromtimestamp(int(taken_at)).astimezone().isoformat(
                timespec="seconds")
        except (OSError, OverflowError, ValueError):
            collected_at = None
    tpi = post.get("text_post_app_info") or {}
    return {
        "content_id": str(pk),
        "title": caption,
        "description": caption,
        "author_id": str(user.get("id") or ""),
        "author_name": user.get("username"),
        "cover_url": candidates[0].get("url") if candidates else None,
        "collected_at": collected_at,
        "statistics": json.dumps({
            "like_count": post.get("like_count"),
            "reply_count": tpi.get("direct_reply_count"),
            "quote_count": tpi.get("quote_count"),
        }, ensure_ascii=False),
        "raw_data": json.dumps(post, ensure_ascii=False),
    }


def parse_play_info(media: dict) -> dict:
    """帖子详情（BarcelonaPostPageTargetQuery 的 data.media）→ PlayerModal 播放信息。

    Threads 响应无时长字段（video_duration 不下发），duration 置 None 前端兜底；
    评论数为 text_post_app_info.direct_reply_count。
    """
    tpi = media.get("text_post_app_info") or {}
    user = media.get("user") or {}
    links = parse_post_links(media)
    videos = [l["url"] for l in links if l.get("kind") == "video" and l.get("url")]
    images = [{"url": l["url"]} for l in links if l.get("kind") == "image" and l.get("url")]
    return {
        "aweme_id": str(media.get("pk") or ""),
        "desc": (media.get("caption") or {}).get("text"),
        "create_time": media.get("taken_at"),
        "aweme_type": 0,
        "duration": None,
        "statistics": {
            "digg_count": media.get("like_count"),
            "comment_count": tpi.get("direct_reply_count"),
            "quote_count": tpi.get("quote_count"),
            "repost_count": tpi.get("repost_count"),
        },
        "author": {"nickname": user.get("username"),
                   "sec_uid": str(user.get("pk") or user.get("id") or "")},
        # CDN 直链（cdninstagram.com）仅 UA 即可访问，媒体代理按域附加 UA
        "video_urls": videos,
        "images": images,
    }


def parse_post_links(media: dict) -> list[dict]:
    """解析帖子详情（BarcelonaPostPageTargetQuery 的 data.media）→ 可下载直链列表。

    视频（media_type=2）：video_versions 取 type=101 的 mp4（102/103 为同链分片变体），
    不附封面图（download_worker 见 image 链接会走图文通道）；
    图文（media_type=1/8）：carousel_media（单图时无该字段，用 media 本体）逐张取
    image_versions2 候选中面积最大者；纯文字（media_type=19）：仅文案（kind=text）。
    """
    links: list[dict] = []

    def _video(v: dict, label: str) -> None:
        url = str(v.get("url") or "")
        if url.startswith("http"):
            links.append({"url": url, "label": label, "kind": "video", "ext": "mp4"})

    videos = [v for v in media.get("video_versions") or [] if v.get("type") == 101]
    width = media.get("original_width") or 0
    height = media.get("original_height") or 0
    for v in videos:
        _video(v, f"视频 {width}x{height}" if width else "视频")

    items = media.get("carousel_media") or [media]
    count = len(items)
    for i, item in enumerate(items, start=1):
        if not videos:
            for v in item.get("video_versions") or []:
                if v.get("type") == 101:
                    _video(v, f"视频 {i}/{count}")
            candidates = ((item.get("image_versions2") or {}).get("candidates") or [])
            if candidates:
                best = max(candidates, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0))
                url = str(best.get("url") or "")
                if url.startswith("http"):
                    links.append({
                        "url": url, "label": f"图片 {i}/{count}", "kind": "image",
                        "ext": "jpg",  # CDN 路径无扩展名
                        "width": best.get("width") or 0, "height": best.get("height") or 0,
                    })

    caption = (media.get("caption") or {}).get("text") or ""
    if caption.strip():
        links.append({"kind": "text", "text": caption, "label": "文案"})
    return links


def _balanced_json(text: str, start: int) -> str | None:
    """从 start（指向 '{'）做括号配平截取一段 JSON 子串；越界/未闭合返回 None。"""
    depth = 0
    in_str = esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_viewer_profile(html: str) -> dict | None:
    """从已登录页面 HTML 的 BarcelonaSharedData 提取当前用户身份。

    任意 threads.com 登录页面的共享数据块（与 lsd 同一份 HTML）：
    ["BarcelonaSharedData",[],{...,"viewer":{"id","username","profile_picture_url",...}}]。
    未登录时无该块或 viewer 为空 → 返回 None（由调用方判定登录态失效）。
    """
    idx = html.find("BarcelonaSharedData")
    if idx < 0:
        return None
    start = html.find("{", idx)
    if start < 0:
        return None
    chunk = _balanced_json(html, start)
    if not chunk:
        return None
    try:
        shared = json.loads(chunk)
    except ValueError:
        logger.debug("BarcelonaSharedData JSON 解析失败")
        return None
    viewer = shared.get("viewer") or {}
    if not viewer.get("id"):
        return None
    return {
        "id": str(viewer.get("id") or ""),
        "username": viewer.get("username"),
        "avatar": viewer.get("profile_picture_url"),
    }


def parse_embedded_saved(html: str) -> dict | None:
    """从 /saved 页面 HTML 提取首屏收藏数据（Relay preloader 内嵌 JSON）。

    首屏列表不发起独立 XHR（浏览器模式仅能拦截到第 2 页起），
    preloader 形如 "xdt_text_app_viewer":{...,"saved_media":{...}}；
    提取失败（页面结构变化）返回 None，调用方回退到仅滚动拦截。
    """
    marker = '"xdt_text_app_viewer":'
    pos = 0
    while True:
        idx = html.find(marker, pos)
        if idx < 0:
            return None
        pos = idx + len(marker)
        start = html.find("{", pos - 1)
        if start < 0:
            continue
        chunk = _balanced_json(html, start)
        if not chunk or "saved_media" not in chunk:
            continue
        try:
            viewer = json.loads(chunk)
        except ValueError:
            logger.debug("preloader JSON 解析失败，跳过该片段")
            continue
        if viewer.get("saved_media"):
            return parse_saved_media({"data": {"xdt_text_app_viewer": viewer}})
        # 首个片段不含收藏数据时继续找下一个 preloader
