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


def parse_following_list(data: dict) -> dict:
    """relation/followings 的 data → {followings, total}。

    pn/ps 偏移分页且响应无 has_more，cursor/has_more 由 api_client 按 total 推导；
    条目精简为展示/入库所需字段（mtime 关注时间 → follow_time ISO）。
    """
    followings = [
        {
            "mid": str(u.get("mid") or ""),
            "nickname": u.get("uname"),
            "avatar_url": u.get("face"),
            "signature": (u.get("sign") or "").strip() or None,
            "follow_time": _ts_iso(u.get("mtime")),
            "special": bool(u.get("special")),
            "official_verify": ((u.get("official_verify") or {}).get("desc")) or None,
        }
        for u in data.get("list") or []
        if u.get("mid")
    ]
    return {"followings": followings, "total": _as_int(data.get("total")) or 0}


def _length_seconds(length) -> int | None:
    """arc/search 的 length（"MM:SS" / "H:MM:SS"）→ 秒。"""
    parts = str(length or "").split(":")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + int(p)
    return seconds


def parse_arc_search(data: dict) -> dict:
    """space/wbi/arc/search 的 data → {items, total}。

    投稿在 data.list.vlist（list_v2 仅部分场景下发，vlist 始终存在）；
    条目 → contents 行字段，collected_at 取发布时间 created（投稿的
    "入库时间"即发布时间，与抖音 parse_aweme 以 create_time 兜底同义）。
    """
    vlist = (data.get("list") or {}).get("vlist") or []
    items = [
        {
            "content_id": v.get("bvid"),
            "title": v.get("title"),
            "description": v.get("description") or None,
            "author_id": str(v.get("mid") or ""),
            "author_name": v.get("author"),
            "cover_url": v.get("pic"),
            "duration": _length_seconds(v.get("length")),
            "statistics": json.dumps(
                {
                    "play": _as_int(v.get("play")),
                    "comment": _as_int(v.get("comment")),
                    "danmaku": _as_int(v.get("video_review")),
                },
                ensure_ascii=False,
            ),
            "raw_data": json.dumps(v, ensure_ascii=False),
            "collected_at": _ts_iso(v.get("created")),
        }
        for v in vlist
        if v.get("bvid")
    ]
    page = data.get("page") or {}
    return {"items": items, "total": _as_int(page.get("count")) or 0}


# playurl quality → 画质名（B 站 qn 编码）
_QN_LABELS = {
    127: "8K 超高清", 126: "杜比视界", 125: "HDR 真彩", 120: "4K 超清",
    116: "1080P60", 112: "1080P 高码率", 80: "1080P 高清", 74: "720P60",
    64: "720P 高清", 32: "480P 清晰", 16: "360P 流畅",
}
# qn → 画面高度（durl mp4 不带分辨率字段，按 qn 推导供画质选链）
_QN_HEIGHTS = {
    127: 4320, 126: 1080, 125: 1080, 120: 2160, 116: 1080, 112: 1080,
    80: 1080, 74: 720, 64: 720, 32: 480, 16: 360,
}
# DASH 同一画质多编码并存时的优先序（avc 兼容性最好）
_CODEC_PRIORITY = ("avc1", "hev1", "hvc1", "av01")


def parse_video_detail(data: dict) -> dict:
    """view 接口的 data → 详情摘要（cid 为 P1 的 cid，多 P 见 pages）。

    statistics 键对齐 follows PlayerModal（digg/comment/collect/share）+ 平台特有
    （play/danmaku），pub_date 为发布时间 epoch 秒（follows 播放信息用）。
    """
    d = data.get("data") or data
    owner = d.get("owner") or {}
    stat = d.get("stat") or {}
    pages = [
        {"page": _as_int(p.get("page")), "cid": str(p.get("cid") or ""),
         "title": p.get("part")}
        for p in (d.get("pages") or []) if p.get("cid")
    ]
    return {
        "bvid": d.get("bvid") or "",
        "aid": str(d.get("aid") or ""),
        "title": d.get("title"),
        "duration": _as_int(d.get("duration")),  # 秒
        "author_id": str(owner.get("mid") or ""),
        "author_name": owner.get("name"),
        "cid": str(d.get("cid") or ""),
        "pages": pages,
        "statistics": json.dumps(
            {
                "play": _as_int(stat.get("view")),
                "danmaku": _as_int(stat.get("danmaku")),
                "digg_count": _as_int(stat.get("like")),
                "comment_count": _as_int(stat.get("reply")),
                "collect_count": _as_int(stat.get("favorite")),
                "share_count": _as_int(stat.get("share")),
            },
            ensure_ascii=False,
        ),
        "pub_date": _as_int(d.get("pubdate")),
    }


def _pick_dash_videos(dash: dict) -> list[tuple[int, int, dict]]:
    """dash.video[] → [(档位高度, qn, stream)]：每个 qn 择一编码（avc 优先），档位降序。

    仅保留高于 720P 的档位（720P 及以下已有 mp4 单文件直链，无需走 DASH）。
    竖屏视频的 v.height 是长边（如 1080P 竖屏实际 1050x1920），画质档位
    必须按 qn 推导：直接用响应 height 会错档（1920/854 匹配不上 1080/480）。
    """
    best: dict[int, tuple[int, dict]] = {}
    for v in dash.get("video") or []:
        qn = _as_int(v.get("id"))
        url = str(v.get("baseUrl") or v.get("base_url") or "")
        if not qn or not url.startswith("http"):
            continue
        codecs = str(v.get("codecs") or "")
        rank = next((i for i, prefix in enumerate(_CODEC_PRIORITY)
                     if codecs.startswith(prefix)), len(_CODEC_PRIORITY))
        cur = best.get(qn)
        if cur is None or rank < cur[0]:
            best[qn] = (rank, v)
    picked = []
    for qn, (_rank, v) in best.items():
        height = _QN_HEIGHTS.get(qn) or _as_int(v.get("height")) or 0
        if height <= 720:
            continue
        picked.append((height, qn, v))
    picked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return picked


def _pick_dash_audio(dash: dict) -> str:
    """dash.audio[] → 最高码率一档的 baseUrl（音质最好且兼容 mp4 容器）。"""
    audios = [a for a in (dash.get("audio") or [])
              if str(a.get("baseUrl") or a.get("base_url") or "").startswith("http")]
    if not audios:
        return ""
    best = max(audios, key=lambda a: _as_int(a.get("bandwidth")) or 0)
    return str(best.get("baseUrl") or best.get("base_url") or "")


def parse_download_links(mp4_data: dict, dash_data: dict | None = None) -> list[dict]:
    """playurl 响应 → 可下载直链列表（首项为推荐地址）。

    mp4_data（platform=html5 请求）：durl 音视频合一单文件（多段时每段一条，
    主链 + backup_url 均收，按 URL 去重）。
    dash_data（fnval=16 请求，需登录态）：高画质 DASH 流 —— 视频流 url 之外附
    audio_url（配套音频流），kind="dash"，由下载器双流下载后 ffmpeg 合并。
    """
    d = (mp4_data.get("data") or {})
    quality = _as_int(d.get("quality")) or 0
    label = _QN_LABELS.get(quality) or f"qn{quality}"
    height = _QN_HEIGHTS.get(quality) or 0
    links: list[dict] = []
    seen: set[str] = set()
    for seg in d.get("durl") or []:
        size = _as_int(seg.get("size"))
        seg_label = label if len(d.get("durl") or []) == 1 else f"{label} 第{seg.get('order') or len(links) + 1}段"
        for url in [seg.get("url")] + (seg.get("backup_url") or []):
            url = str(url or "")
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            links.append({
                "url": url, "label": seg_label, "ext": "mp4", "kind": "video",
                "size": size, "height": height,
            })

    if dash_data:
        dash = (dash_data.get("data") or {}).get("dash") or {}
        audio_url = _pick_dash_audio(dash)
        for dash_height, qn, v in _pick_dash_videos(dash):
            links.append({
                "url": str(v.get("baseUrl") or v.get("base_url") or ""),
                "label": f"{_QN_LABELS.get(qn) or f'qn{qn}'} DASH",
                "ext": "mp4", "kind": "dash",
                "width": _as_int(v.get("width")) or 0, "height": dash_height,
                "audio_url": audio_url,
            })
    return links
