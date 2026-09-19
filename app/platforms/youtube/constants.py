"""YouTube 平台常量。"""

PLATFORM = "youtube"
DISPLAY_NAME = "YouTube"

HOME_URL = "https://www.youtube.com/"

# InnerTube API（YouTube 网页端底层接口，POST JSON；key/clientVersion 从首页
# HTML 的 ytcfg 提取，见 api_client._ensure_ytcfg）
INNERTUBE_BROWSE_API = "https://www.youtube.com/youtubei/v1/browse"

# 订阅列表 feed（需登录态 + SAPISIDHASH authorization 头）
SUBSCRIPTIONS_BROWSE_ID = "FEchannels"
# 频道 Videos tab 的 browse params（protobuf base64，全网稳定常量）
VIDEOS_TAB_PARAMS = "EgZ2aWRlb3PyBgQKAjoA"

PAGE_SIZE = 30                # richGrid 每页条数（2026 前端实测）
API_PAGE_INTERVAL_SEC = 0.5   # API 直连翻页间隔（防风控）

# 判定已登录的 cookie（任一存在且非空即视为登录，与 adapter._COOKIE_KEYS 一致）
LOGIN_COOKIE_KEYS = ("SID", "SAPISID", "__Secure-3PSID", "LOGIN_INFO")
# 生成 SAPISIDHASH authorization 头所用 cookie（按序取第一个存在的）
AUTH_COOKIE_KEYS = ("SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID")
