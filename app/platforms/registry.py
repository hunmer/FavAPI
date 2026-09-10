"""平台适配器注册表：新增平台只需实现 Adapter 并在此注册。"""
from app.platforms.base import BasePlatformAdapter

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


def _info(adapter: BasePlatformAdapter) -> dict:
    return {
        "platform": adapter.platform,
        "display_name": adapter.display_name,
        "implemented": adapter.implemented,
        "supported_actions": list(adapter.supported_actions),
    }


# 导入即注册（抖音 / Bilibili / 小红书）
from app.platforms.bilibili.adapter import BilibiliAdapter  # noqa: E402
from app.platforms.douyin.adapter import DouyinAdapter  # noqa: E402
from app.platforms.xiaohongshu.adapter import XiaohongshuAdapter  # noqa: E402

register(DouyinAdapter())
register(BilibiliAdapter())
register(XiaohongshuAdapter())
