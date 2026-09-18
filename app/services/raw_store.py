"""raw_data 外置文件存储：data/raw_data/{platform}/{content_id}.json。

原始响应 JSON 体积大且不参与 SQL 查询，入库时落到独立文件，contents 表不再
保存原文以控制 favapi.db 体积。
"""
import json
import re
import shutil
from pathlib import Path

from app import config


def _safe_id(value) -> str:
    """文件名安全化（与封面缓存同规则）：非法字符折叠为下划线，截断 120 字符。"""
    return re.sub(r"[^\w.-]+", "_", str(value).strip())[:120] or "_"


def raw_path(platform, content_id) -> Path:
    return config.DATA_DIR / "raw_data" / _safe_id(platform) / f"{_safe_id(content_id)}.json"


def save(platform: str, content_id: str, raw) -> None:
    """写入原始 JSON（str/dict 均可；空值跳过）。"""
    if not raw:
        return
    if not isinstance(raw, str):
        raw = json.dumps(raw, ensure_ascii=False)
    path = raw_path(platform, content_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")


def load(platform: str, content_id: str) -> dict:
    """读取原始 JSON；文件缺失或损坏返回空 dict。"""
    try:
        value = json.loads(raw_path(platform, content_id).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def delete_many(rows: list[dict]) -> int:
    """删除这些内容行（platform/content_id）对应的 raw_data 文件；返回删除数。"""
    deleted = 0
    for r in rows:
        try:
            raw_path(r.get("platform"), r.get("content_id")).unlink()
            deleted += 1
        except OSError:
            pass  # 文件被占用等，留给下次全量清理
    return deleted


def clear_raw_dir() -> int:
    """清空整个 raw_data 目录（重置收藏夹等全量清理场景）；返回删除的文件数。"""
    root = config.DATA_DIR / "raw_data"
    if not root.exists():
        return 0
    n = sum(1 for p in root.rglob("*") if p.is_file())
    shutil.rmtree(root, ignore_errors=True)
    return n
