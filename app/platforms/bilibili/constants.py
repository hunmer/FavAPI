"""Bilibili 平台常量。"""

PLATFORM = "bilibili"
DISPLAY_NAME = "Bilibili"

HOME_URL = "https://www.bilibili.com/"

# 收藏夹公开接口（GET；带浏览器登录态请求可降低风控概率）
# list-all：某用户的收藏夹列表（含 media_id / 标题 / 数量）
FAV_FOLDER_LIST_API = "https://api.bilibili.com/x/v3/fav/folder/created/list-all"
# resource/list：单个收藏夹内容，pn/ps 翻页
FAV_RESOURCE_LIST_API = "https://api.bilibili.com/x/v3/fav/resource/list"
# nav：当前登录用户信息（uname / face / mid）
NAV_API = "https://api.bilibili.com/x/web-interface/nav"
# batch-del：批量删除收藏夹内资源（POST 表单，resources=id:type 逗号拼接，
# csrf 参数需 cookie 中 bili_jct）
FAV_BATCH_DEL_API = "https://api.bilibili.com/x/v3/fav/resource/batch-del"
# folder/edit：编辑收藏夹（POST 表单；cover 必传，缺省会清空封面）
FAV_FOLDER_EDIT_API = "https://api.bilibili.com/x/v3/fav/folder/edit"
# folder/del：删除收藏夹（POST multipart 表单；默认收藏夹不可删）
FAV_FOLDER_DEL_API = "https://api.bilibili.com/x/v3/fav/folder/del"

# 视频详情（GET view：bvid → cid/pages/标题/作者；无需 WBI 签名，匿名可用）
VIDEO_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
# 播放直链（GET playurl：需 WBI 签名，密钥取自 nav 的 wbi_img）。
# platform=html5 + fnval=1 返回音视频合一的 mp4 单文件 durl（匿名最高 720P）；
# fnval=16 返回 DASH 高画质流（需登录态，1080P+/4K），音视频分离，由
# download_worker 双流下载后 ffmpeg -c copy 合并
PLAYER_PLAYURL_API = "https://api.bilibili.com/x/player/wbi/playurl"

# playurl 请求画质（html5 mp4 端点 qn>64 返回空，64=720P 为主选，16=360P 兜底）
PLAYURL_QN_FALLBACKS = (64, 16)

BATCH_DEL_SIZE = 20            # 批量删除单批条数（与抖音取消收藏同量级考量）
BATCH_DEL_INTERVAL_SEC = 0.5   # 批次间隔，防风控
API_PAGE_INTERVAL_SEC = 0.8    # API 直连翻页间隔（防风控，同抖音量级）

# 判定已登录的 cookie（任一存在且非空即视为登录）
LOGIN_COOKIE_KEYS = ("SESSDATA",)

DEFAULT_COUNT = 0          # 不填 count 时抓全部（0 = 无上限）
MAX_COUNT = 500
PAGE_SIZE = 36            # 网页端每页条数
PAGE_INTERVAL_MS = 800    # 翻页请求间隔，防风控
MAX_PAGES = 200           # 单收藏夹翻页上限
