"""抖音平台常量。"""

PLATFORM = "douyin"
DISPLAY_NAME = "抖音"

HOME_URL = "https://www.douyin.com/"
FAVORITES_URL = "https://www.douyin.com/user/self?showTab=favorite_collection"

# 个人收藏列表接口（响应拦截匹配用）
LISTCOLLECTION_API = "/aweme/v1/web/aweme/listcollection"

# API 直连抓取用（POST，body 为 count/cursor；浏览器走页面时不需要）
LISTCOLLECTION_URL = "https://www.douyin.com/aweme/v1/web/aweme/listcollection/"
API_PAGE_COUNT = 20          # API 直连每页条数（服务端单页上限 20）
API_PAGE_INTERVAL_SEC = 0.8  # API 直连翻页间隔（防风控节流）

# 批量取消收藏（POST，body 为 aweme_ids / aweme_type_map）
CANCEL_COLLECT_URL = "https://www.douyin.com/aweme/v1/web/aweme/cancel/collect/multi/"
CANCEL_COLLECT_SINGLE_URL = "https://www.douyin.com/aweme/v1/web/aweme/collect/"
CANCEL_COLLECT_BATCH = 20    # 降低单批参数异常概率；接口允许更大批次
CANCEL_COLLECT_INTERVAL_SEC = 0.5
CANCEL_COLLECT_RETRIES = 3   # status_code=5（限流/风控）时的重试次数

# 点赞（喜欢）相关接口（完整 URL 供直连用；*_PATH 供浏览器页面 fetch 用）
DIGG_URL = "https://www.douyin.com/aweme/v1/web/commit/item/digg/"
CANCEL_DIGG_MULTI_URL = "https://www.douyin.com/aweme/v1/web/cancel/item/digg/multi/"
DIGG_URL_PATH = "/aweme/v1/web/commit/item/digg/"
CANCEL_DIGG_MULTI_URL_PATH = "/aweme/v1/web/cancel/item/digg/multi/"
# 喜欢(点赞) tab 列表，注意与收藏(listcollection)区分
LIKE_LIST_URL = "https://www.douyin.com/aweme/v1/web/aweme/favorite/"
# 观看历史（强校验接口，需活跃登录态）/ 稍后再看（offset 偏移分页）
HISTORY_URL = "https://www.douyin.com/aweme/v1/web/history/read/"
WATCHLATER_URL = "https://www.douyin.com/aweme/v1/web/watchlater/list/"
CANCEL_DIGG_BATCH = 20          # 批量取消点赞单批条数（与取消收藏同量级考量）
CANCEL_DIGG_INTERVAL_SEC = 0.5
CANCEL_DIGG_RETRIES = 3         # status_code=5（限流/风控）时的重试次数

# 当前登录用户资料接口（个人主页加载时页面自身会调用，拦截复用；签名由页面 JS 完成）
PROFILE_SELF_API = "/aweme/v1/web/user/profile/self"

# 视频详情接口（按 aweme_id 解析播放直链；GET 读接口，可 curl_cffi 直连）
AWEME_DETAIL_URL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

# 判定已登录的 cookie（任一存在且非空即视为登录）
LOGIN_COOKIE_KEYS = ("sessionid", "sessionid_ss")

DEFAULT_COUNT = 20
MAX_COUNT = 500
SCROLL_INTERVAL_MS = 1800   # 每次滚动后等待响应的间隔
MAX_SCROLL_ROUNDS = 300     # 滚动轮数上限，防死循环
MAX_STALL_ROUNDS = 6        # 连续 N 轮滚动无新增数据则提前结束（页面到底/滚动失效）
