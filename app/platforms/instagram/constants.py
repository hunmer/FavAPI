"""Instagram 平台常量。"""

PLATFORM = "instagram"
DISPLAY_NAME = "Instagram"

HOME_URL = "https://www.instagram.com/"

# REST v1 接口基址（收藏 / 关注 / 作品详情；GET，翻页回传 next_max_id）
API_BASE = "https://www.instagram.com/api/v1"
SAVED_PATH = "/feed/saved/posts/"          # 收藏列表（items[].media 嵌套）
FOLLOWING_PATH = "/friendships/{user_id}/following/"  # 关注列表（max_id 为偏移量）
MEDIA_INFO_PATH = "/media/{media_id}/info/"           # 作品详情（items[0]）
USER_INFO_PATH = "/users/{user_id}/info/"             # 用户资料（含登录用户自己）

# 博主投稿列表 GraphQL（POST /graphql/query，form-urlencoded）。
# 2026-09 抓包：PolarisProfilePostsTabContentQuery_connection，连接挂在根字段
# xdt_api__v1__feed__user_timeline_graphql_connection 下（edges[].node / page_info）；
# variables 以 username 定位博主（不认数字 pk），end_cursor 形如 "{media_pk}_{user_pk}"。
# 若出现 GraphQL execution error，多为前端发版改了持久化查询，需重新抓包更新 doc_id。
GRAPHQL_URL = "https://www.instagram.com/graphql/query"
USER_POSTS_DOC_ID = "38491138490501953"
USER_POSTS_QUERY_NAME = "PolarisProfilePostsTabContentQuery_connection"
USER_POSTS_ROOT_FIELD = "xdt_api__v1__feed__user_timeline_graphql_connection"

# x-ig-app-id（Instagram Web 固定值）
APP_ID = "936619743392459"

# Relay @relayPv 持久化变量标志（2026-09 抓包原样固化，缺失报 GraphQL 错误）
USER_POSTS_PV_FLAGS = {
    "__relay_internal__pv__PolarisMultiCaptionCarouselEnabledrelayprovider": True,
    "__relay_internal__pv__PolarisShortDramaEnabledrelayprovider": False,
    "__relay_internal__pv__PolarisReelsRecoDebugOverlayEnabledrelayprovider": False,
}

# 写操作 mutation（POST /api/graphql，2026-09 全部实测往返验证通过）。
# form 带 av(=fbid_v2) + fb_dtsg + lsd 全集（与浏览器抓包一致）；like 的 variables
# 带 actor_id + client_mutation_id（用户抓包原样），unlike/save/unsave 仅 media_id
# （站点 bundle PolarisAPI*Post 模块源码形态）。doc_id 随版本轮换，失效时重新
# 抓包或查公开逆向仓库更新。REST fallback 路径（web/likes/{id}/like|unlike/、
# web/save/{id}/save|unsave/，POST 空 body）实测 404 已不放行，勿走。
API_GRAPHQL_URL = "https://www.instagram.com/api/graphql"
LIKE_DOC_ID = "27358573637160660"
LIKE_QUERY_NAME = "PolarisAPILikePostMutation"
UNLIKE_DOC_ID = "37071567952434061"
UNLIKE_QUERY_NAME = "PolarisAPIUnlikePostMutation"
SAVE_DOC_ID = "27326721586982367"
SAVE_QUERY_NAME = "PolarisAPISavePostMutation"
UNSAVE_DOC_ID = "35746443864970251"
UNSAVE_QUERY_NAME = "PolarisAPIUnsavePostMutation"

# 直连每页条数（与浏览器抓包一致）；翻页间隔（防风控节流）。
# 2026-09 实测：连续 20+ 个混合直连请求即触发会话挑战（全部请求 302 循环回
# instagram.com/#），间隔放宽到 2s 并避免高频连续调用。
SAVED_PAGE_COUNT = 12
FOLLOWING_PAGE_COUNT = 12
USER_POSTS_PAGE_COUNT = 12
API_PAGE_INTERVAL_SEC = 2.0
WRITE_INTERVAL_SEC = 1.0   # 连续写操作（点赞等）间隔

# 判定已登录的 cookie（任一存在且非空即视为登录）
LOGIN_COOKIE_KEYS = ("sessionid", "ds_user_id")

# 博主主键（follow_authors.sec_uid）= username，格式约束
USERNAME_PATTERN = r"^[A-Za-z0-9._]{1,30}$"
