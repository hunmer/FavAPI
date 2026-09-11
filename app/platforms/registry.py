"""平台适配器注册表：新增平台只需实现 Adapter 并在此注册。"""
from app.platforms.base import BasePlatformAdapter
import json, logging
from pathlib import Path
from app.platforms.declarative import DeclarativeAdapter
from app import config

logger = logging.getLogger("favapi.platforms")

_adapters: dict[str, BasePlatformAdapter] = {}


def register(adapter: BasePlatformAdapter):
    _adapters[adapter.platform] = adapter


def get_adapter(platform: str) -> BasePlatformAdapter | None:
    return _adapters.get(platform)


def get_platform_info(platform: str) -> dict | None:
    adapter = _adapters.get(platform)
    return _info(adapter) if adapter else None


def platform_infos() -> list[dict]:
    """全部平台元信息（供 Web 界面平台下拉框 / API 使用）。"""
    return [_info(a) for a in _adapters.values()]

def load_declarative(directory=None) -> list[str]:
    """扫描目录下 */platform.json，加载或替换声明式平台。"""
    loaded=[]; root=Path(directory or config.PLATFORMS_DIR)
    if not root.exists(): return loaded
    for path in root.glob("*/platform.json"):
        try:
            spec=json.loads(path.read_text(encoding="utf-8")); adapter=DeclarativeAdapter(spec, base_dir=path.parent)
            register(adapter); loaded.append(adapter.platform)
        except Exception as exc:
            logger.warning("平台声明加载失败 %s: %s", path, exc)
    return loaded


def _info(adapter: BasePlatformAdapter) -> dict:
    info = {
        "platform": adapter.platform,
        "display_name": adapter.display_name,
        "implemented": adapter.implemented,
        "supported_actions": list(adapter.supported_actions),
    }
    if adapter.icon:
        info["icon_url"] = f"/api/v1/platforms/{adapter.platform}/icon"
    return info


# 导入即注册（抖音 / Bilibili / 小红书）
from app.platforms.bilibili.adapter import BilibiliAdapter  # noqa: E402
from app.platforms.douyin.adapter import DouyinAdapter  # noqa: E402
from app.platforms.xiaohongshu.adapter import XiaohongshuAdapter  # noqa: E402
from app.platforms.youtube.adapter import YouTubeAdapter  # noqa: E402
from app.platforms.wechat.adapter import WeChatAdapter  # noqa: E402

register(DouyinAdapter())
register(BilibiliAdapter())
register(XiaohongshuAdapter())
register(WeChatAdapter())
load_declarative()
register(YouTubeAdapter(config.PLATFORMS_DIR / "youtube"))
