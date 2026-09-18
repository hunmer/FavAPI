"""小红书平台常量。"""

PLATFORM = "xiaohongshu"
DISPLAY_NAME = "小红书"

HOME_URL = "https://www.xiaohongshu.com/"
# 收藏 tab 页面（必须带 user_id：/user/profile 不带 id 是 404 页，当前登录用户 id 由 adapter 解析）
PROFILE_URL = "https://www.xiaohongshu.com/user/profile/{user_id}?tab=fav&subTab=note"

# 收藏列表接口（响应拦截匹配用）；edith 接口有 x-s/x-t 签名校验，只能拦截页面自身请求
COLLECT_PAGE_API = "/api/sns/web/v2/note/collect/page"
# 当前用户信息接口（页面通道：需页面内 _webmsxyw 函数签名后请求）
USER_ME_API = "https://edith.xiaohongshu.com/api/sns/web/v2/user/me"

# API 直连用完整 URL（签名由 xhshow 纯算生成，见 api_client.py）
USER_ME_URL = USER_ME_API
COLLECT_PAGE_URL = "https://edith.xiaohongshu.com/api/sns/web/v2/note/collect/page"
LIKE_PAGE_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/note/like/page"
API_PAGE_COUNT = 30            # API 直连每页条数（与浏览器抓包一致）
API_PAGE_INTERVAL_SEC = 1.2    # 翻页间隔（小红书风控较严，慢于抖音）

# 笔记详情接口（POST JSON；xsec_token 强校验——空/错 token → 461 code=300031，
# token 来自收藏/点赞列表响应 notes[].xsec_token；xsec_source 实测不校验，固定 pc_feed）
NOTE_DETAIL_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"

# 写操作接口（POST JSON，body 字段名各异见 api_client.py；签名与读接口同链路）
COLLECT_NOTE_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/note/collect"
UNCOLLECT_NOTE_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/note/uncollect"
LIKE_NOTE_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/note/like"
DISLIKE_NOTE_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/note/dislike"
UNCOLLECT_BATCH = 20            # 批量取消收藏单批条数（对齐抖音量级，防参数过长）
UNCOLLECT_INTERVAL_SEC = 0.5    # 批间间隔（防风控）

# 判定已登录的 cookie（任一存在且非空即视为登录）。
# 注意：web_session 游客也有（实测游客前缀 03/登录 04，不可靠）；id_token 仅登录后存在。
LOGIN_COOKIE_KEYS = ("id_token",)

DEFAULT_COUNT = 20
MAX_COUNT = 500
SCROLL_INTERVAL_MS = 1800   # 每次滚动后等待响应的间隔
MAX_SCROLL_ROUNDS = 300     # 滚动轮数上限，防死循环
MAX_STALL_ROUNDS = 8        # 连续 N 轮滚动无新增数据则提前结束（页面到底/滚动失效）
