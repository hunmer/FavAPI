"""抖音平台常量。"""

PLATFORM = "douyin"
DISPLAY_NAME = "抖音"

HOME_URL = "https://www.douyin.com/"
FAVORITES_URL = "https://www.douyin.com/user/self?showTab=favorite_collection"

# 个人收藏列表接口（响应拦截匹配用）
LISTCOLLECTION_API = "/aweme/v1/web/aweme/listcollection"

# 当前登录用户资料接口（个人主页加载时页面自身会调用，拦截复用；签名由页面 JS 完成）
PROFILE_SELF_API = "/aweme/v1/web/user/profile/self"

# 判定已登录的 cookie（任一存在且非空即视为登录）
LOGIN_COOKIE_KEYS = ("sessionid", "sessionid_ss")

DEFAULT_COUNT = 20
MAX_COUNT = 500
SCROLL_INTERVAL_MS = 1800   # 每次滚动后等待响应的间隔
MAX_SCROLL_ROUNDS = 300     # 滚动轮数上限，防死循环
MAX_STALL_ROUNDS = 6        # 连续 N 轮滚动无新增数据则提前结束（页面到底/滚动失效）
