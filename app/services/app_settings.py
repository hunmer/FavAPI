"""运行参数设置（settings.json）读写：api 与 services 共用。"""
import json
import logging
from pathlib import Path

from app.config import DATA_DIR

logger = logging.getLogger("favapi.settings")

SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "profile_path": str(DATA_DIR / "profiles"),
    "headless": False,
    "request_interval": 2.0,
    "request_timeout": 30,
    "download_dir": "",            # 下载根目录，空 = data/downloads
    "download_concurrency": 1,     # 并发下载数
    "download_quality": "auto",    # 平台下载默认清晰度（auto = 平台推荐）
    "aria2_rpc_port": 6800,        # aria2c RPC 端口
    "aria2_connections": 8,        # aria2c 单任务连接分片数
}

# 平台下载可选清晰度档位（auto + 常见高度）
QUALITY_OPTIONS = ("auto", "2160", "1440", "1080", "720", "540", "480")


def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            data.update(json.loads(SETTINGS_PATH.read_text("utf-8")))
        except (json.JSONDecodeError, OSError):
            logger.warning("settings.json 解析失败，回退默认设置")
    return data


def save_settings(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
