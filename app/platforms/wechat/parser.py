"""WeChatDataAnalysis messages.json 解析器。"""
import json
from datetime import datetime


def _iso_timestamp(value):
    try:
        ts = float(value)
        return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def parse_message(message: dict) -> dict | None:
    """将导出消息映射为 favorites/content 通用字段。"""
    content_id = str(message.get("id") or message.get("serverId") or message.get("localId") or "").strip()
    if not content_id:
        return None
    title = message.get("title") or message.get("content") or message.get("locationPoiname")
    url = message.get("url") or message.get("locationLabel") or None
    return {
        "content_id": content_id,
        "title": title or None,
        "description": message.get("content") or None,
        "author_id": message.get("senderUsername") or None,
        "author_name": message.get("senderDisplayName") or message.get("senderUsername") or None,
        "cover_url": message.get("imageUrl") or message.get("thumbUrl") or None,
        "url": url,
        "raw_data": json.dumps(message, ensure_ascii=False),
        "collected_at": _iso_timestamp(message.get("createTime")),
    }


def parse_export(data: dict) -> list[dict]:
    messages = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list):
        raise ValueError("JSON 文件缺少 messages 数组（请使用 WeChatDataAnalysis 导出的 messages.json）")
    return [item for msg in messages if isinstance(msg, dict) if (item := parse_message(msg))]

