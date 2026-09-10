"""小红书平台常量。"""

PLATFORM = "xiaohongshu"
DISPLAY_NAME = "小红书"

HOME_URL = "https://www.xiaohongshu.com/"
# 收藏 tab 页面（必须带 user_id：/user/profile 不带 id 是 404 页，当前登录用户 id 由 adapter 解析）
PROFILE_URL = "https://www.xiaohongshu.com/user/profile/{user_id}?tab=fav&subTab=note"

# 收藏列表接口（响应拦截匹配用）；edith 接口有 x-s/x-t 签名校验，只能拦截页面自身请求
COLLECT_PAGE_API = "/api/sns/web/v2/note/collect/page"
# 当前用户信息接口（需页面内 _webmsxyw 函数签名后请求）
USER_ME_API = "https://edith.xiaohongshu.com/api/sns/web/v2/user/me"

# 判定已登录的 cookie（任一存在且非空即视为登录）。
# 注意：web_session 游客也有（实测游客前缀 03/登录 04，不可靠）；id_token 仅登录后存在。
LOGIN_COOKIE_KEYS = ("id_token",)

DEFAULT_COUNT = 20
MAX_COUNT = 500
SCROLL_INTERVAL_MS = 1800   # 每次滚动后等待响应的间隔
MAX_SCROLL_ROUNDS = 300     # 滚动轮数上限，防死循环
MAX_STALL_ROUNDS = 8        # 连续 N 轮滚动无新增数据则提前结束（页面到底/滚动失效）
