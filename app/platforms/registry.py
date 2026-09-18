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


def _target_params(params) -> list[dict]:
    return [
        {
            "key": p.key, "label": p.label, "type": p.type,
            "required": p.required, "placeholder": p.placeholder, "help": p.help,
            "options": [{"value": v, "label": n} for v, n in p.options],
        }
        for p in params
    ]


def _info(adapter: BasePlatformAdapter) -> dict:
    info = {
        "platform": adapter.platform,
        "display_name": adapter.display_name,
        "implemented": adapter.implemented,
        "supported_actions": list(adapter.supported_actions),
        "api_fetch_implemented": adapter.api_fetch_implemented,
        # 是否提供「平台下载」（按视频 ID 解析直链交给 aria2c）；前端下载弹窗据此默认平台下载
        "download_api_implemented": adapter.download_api_implemented,
        # 是否支持特别关注体系（关注列表 / 博主主页作品 / 一键同步）；前端账号详情 Tab 据此渲染
        "follows_api_implemented": adapter.follows_api_implemented,
        # 可抓取入库的列表目标（收藏/喜欢/稍后再看…），前端渲染卡片 + 弹窗表单
        "fetch_targets": [
            {
                "action": t.action,
                "name": t.name,
                "description": t.description,
                "source": t.source,
                "params": _target_params(t.params),
            }
            for t in adapter.effective_fetch_targets()
        ],
        "api_operations": [
            {
                "op_id": op.op_id,
                "name": op.name,
                "description": op.description,
                "danger": op.danger,
                "params": _target_params(op.params),
            }
            for op in adapter.api_operations
        ],
    }
    if adapter.icon:
        info["icon_url"] = f"/api/v1/platforms/{adapter.platform}/icon"
    return info


# 导入即注册（抖音 / Bilibili / 小红书）
from app.platforms.bilibili.adapter import BilibiliAdapter  # noqa: E402
from app.platforms.douyin.adapter import DouyinAdapter  # noqa: E402
from app.platforms.kuaishou.adapter import KuaishouAdapter  # noqa: E402
from app.platforms.threads.adapter import ThreadsAdapter  # noqa: E402
from app.platforms.tiktok.adapter import TikTokAdapter  # noqa: E402
from app.platforms.xiaohongshu.adapter import XiaohongshuAdapter  # noqa: E402
from app.platforms.youtube.adapter import YouTubeAdapter  # noqa: E402
from app.platforms.wechat.adapter import WeChatAdapter  # noqa: E402

register(DouyinAdapter())
register(BilibiliAdapter())
register(XiaohongshuAdapter())
register(WeChatAdapter())
load_declarative()
register(YouTubeAdapter(config.PLATFORMS_DIR / "youtube"))
register(ThreadsAdapter(config.PLATFORMS_DIR / "threads"))
# 快手：声明式注册之上叠加 API 直连能力（浏览器模式仍走 DeclarativeAdapter）
register(KuaishouAdapter(config.PLATFORMS_DIR / "kuaishou"))
# TikTok：同快手模式，外部声明 + API 直连（收藏/点赞/用户信息）
register(TikTokAdapter(config.PLATFORMS_DIR / "tiktok"))
