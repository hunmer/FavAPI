"""Threads 平台常量。"""

PLATFORM = "threads"
DISPLAY_NAME = "Threads"

HOME_URL = "https://www.threads.com/"
FAVORITES_URL = "https://www.threads.com/saved"

# 收藏（已保存）列表 GraphQL 接口（POST，form-urlencoded）
GRAPHQL_URL = "https://www.threads.com/graphql/query"
# 2026-09 抓包：BarcelonaSavedPageRefetchableQuery（首屏数据嵌在 /saved HTML 的
# Relay preloader 里，该 doc_id 同时覆盖首页（省略 after）与翻页（传 end_cursor））。
# 若出现 GraphQL execution error，多为前端发版改了持久化查询，需重新抓包更新。
SAVED_DOC_ID = "28286471504347695"
SAVED_QUERY_NAME = "BarcelonaSavedPageRefetchableQuery"
APP_ID = "238260118697367"        # x-ig-app-id（Threads Web 固定值）
APP_VIEWER_ID = "17841470825299776"  # av（应用 viewer id，非用户 id）

# 直连每页条数（服务端实际单页返回 ~10 条）；翻页间隔（防风控节流）
API_PAGE_COUNT = 12
API_PAGE_INTERVAL_SEC = 1.0

# Relay @relayPv 持久化变量标志（2026-09 抓包原样固化）。
# 必需：缺失时服务端返回 GraphQL execution error；布尔值与浏览器一致。
SAVED_PV_FLAGS = {
    "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasPrivateRepliesDeprecationrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasDearAlgoConsumptionrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasMetaAiContentAttachmentsrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasEventBadgerelayprovider": False,
    "__relay_internal__pv__BarcelonaGenAIRepliesEnabledrelayprovider": False,
    "__relay_internal__pv__BarcelonaIsSearchDiscoveryEnabledrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasCommunitiesrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasGameScoreSharerelayprovider": True,
    "__relay_internal__pv__BarcelonaMessagesHasLiveChatMessagingrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasPublicViewCountCardrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasCommunityEmojiUpdateCardrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasCommunityEntityCardrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasScorecardCommunityrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasSportTeamAllegianceCardrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasMusicrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasNewspaperLinkStylerelayprovider": False,
    "__relay_internal__pv__BarcelonaHasMessagingrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasPodcastV2Consumptionrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasPodcastTranscriptConsumptionrelayprovider": True,
    "__relay_internal__pv__BarcelonaShouldFulfillLightboxQueryrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasViewerRepliedrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasGhostPostEmojiActivationrelayprovider": False,
    "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasDearAlgoWebProductionrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasWebFaviconsrelayprovider": False,
    "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasCommunityTopContributorsrelayprovider": False,
    "__relay_internal__pv__BarcelonaCanSeeSponsoredContentrelayprovider": False,
    "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": True,
    "__relay_internal__pv__BarcelonaIsInternalUserrelayprovider": False,
}

# 判定已登录的 cookie（任一存在且非空即视为登录）
LOGIN_COOKIE_KEYS = ("sessionid", "ds_user_id")

# 收藏 / 取消收藏 mutation（2026-09 抓包；与读接口同套最小字段集直连，无需 fb_dtsg）。
# variables: {"media_id": "<帖子 pk>", "module": "ig_text_post_permalink"}；
# 成功响应 data.data.media.has_viewer_saved：save=True / unsave=null
SAVE_DOC_ID = "29005633985708481"
SAVE_QUERY_NAME = "useBarcelonaSaveMutationSaveMutation"
UNSAVE_DOC_ID = "27999013096419149"
UNSAVE_QUERY_NAME = "useBarcelonaSaveMutationUnsaveMutation"
SAVE_MODULE = "ig_text_post_permalink"  # 埋点字段，实测取值不影响结果
UNSAVE_INTERVAL_SEC = 0.5     # 批量取消收藏间隔（防风控节流）

DEFAULT_COUNT = 20
MAX_COUNT = 500
WAIT_AFTER_GOTO_MS = 5000   # 打开收藏页后等待首批数据渲染
SCROLL_INTERVAL_MS = 1800   # 每次滚动后等待响应的间隔
MAX_SCROLL_ROUNDS = 300     # 滚动轮数上限，防死循环
MAX_STALL_ROUNDS = 6        # 连续 N 轮滚动无新增数据则提前结束
