"""TikTok 平台常量。"""

PLATFORM = "tiktok"
DISPLAY_NAME = "TikTok"

HOME_URL = "https://www.tiktok.com/favorites"
HOMEPAGE = "https://www.tiktok.com"

# 收藏列表（私密，强登录态校验；游标 cursor 为毫秒时间戳，首页 0）
COLLECT_LIST_URL = "https://www.tiktok.com/api/user/collect/item_list/"
# 点赞列表（半公开：仅公开点赞的用户可见，本人私密点赞返回空列表）
LIKE_LIST_URL = "https://www.tiktok.com/api/favorite/item_list/"
# 当前登录用户信息（webapp 身份来源，无签名要求；JS Reverse 定位）
APP_CONTEXT_URL = "https://www.tiktok.com/node-webapp/api/common-app-context"
# 帖子详情数据源：帖子页 HTML 的 SSR 段（webapp.video-detail，公开访客可见）。
# URL 中 handle 不参与定位（占位即可）；图文帖必须用 /video/ 路径才有 SSR 详情。
POST_DETAIL_URL = "https://www.tiktok.com/@tiktok/video/{item_id}"

# 判定 API 直连登录态的 cookie
LOGIN_COOKIE_KEYS = ("sessionid",)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

API_PAGE_COUNT = 16          # API 直连单页条数（与浏览器一致最稳）
API_PAGE_INTERVAL_SEC = 1.0  # API 直连翻页间隔（防风控节流）

# 浏览器拦截模式（collect 直连被拦时的降级通道）滚动控制
MAX_SCROLL_ROUNDS = 30
MAX_STALL_ROUNDS = 6

DEFAULT_COUNT = 0            # 不填 count 时抓全部（0 = 无上限）
MAX_COUNT = 500
