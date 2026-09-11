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

# 判定已登录的 cookie（任一存在且非空即视为登录）
LOGIN_COOKIE_KEYS = ("SESSDATA",)

DEFAULT_COUNT = 20
MAX_COUNT = 500
PAGE_SIZE = 36            # 网页端每页条数
PAGE_INTERVAL_MS = 800    # 翻页请求间隔，防风控
MAX_PAGES = 200           # 单收藏夹翻页上限
