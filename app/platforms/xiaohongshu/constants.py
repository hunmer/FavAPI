"""小红书平台常量。"""

PLATFORM = "xiaohongshu"
DISPLAY_NAME = "小红书"

HOME_URL = "https://www.xiaohongshu.com/"
# 个人主页收藏 tab（不带用户 id 时由站点跳转到当前登录用户主页）
FAVORITES_URL = "https://www.xiaohongshu.com/user/profile?tab=fav&subTab=note"
# 指定目标用户时使用：/user/profile/{user_id}?tab=fav&subTab=note
PROFILE_URL = "https://www.xiaohongshu.com/user/profile/{user_id}?tab=fav&subTab=note"

# 收藏列表接口（响应拦截匹配用）；edith 接口有 x-s/x-t 签名校验，只能拦截页面自身请求
COLLECT_PAGE_API = "/api/sns/web/v2/note/collect/page"

# 判定已登录的 cookie（任一存在且非空即视为登录）
LOGIN_COOKIE_KEYS = ("web_session",)

DEFAULT_COUNT = 20
MAX_COUNT = 500
SCROLL_INTERVAL_MS = 1800   # 每次滚动后等待响应的间隔
MAX_SCROLL_ROUNDS = 300     # 滚动轮数上限，防死循环
MAX_STALL_ROUNDS = 8        # 连续 N 轮滚动无新增数据则提前结束（页面到底/滚动失效）
