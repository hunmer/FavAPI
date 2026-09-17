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
