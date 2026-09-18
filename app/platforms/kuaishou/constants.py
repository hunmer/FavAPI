"""快手平台常量。"""

PLATFORM = "kuaishou"
DISPLAY_NAME = "快手"

HOME_URL = "https://www.kuaishou.com/"

# 用户信息（GET，无参数返回当前登录用户；响应含 eid/userName/userId/fans 等）
PROFILE_URL = "https://www.kuaishou.com/rest/v/profile/get"
# 收藏列表（POST JSON body：userId=用户 eid，pcursor 翻页游标，page 固定 "collect"）
COLLECT_LIST_URL = "https://www.kuaishou.com/rest/v/collect/list"
# 点赞列表（POST JSON body：pcursor 翻页游标，page 固定 "profile"）
FEED_LIKED_URL = "https://www.kuaishou.com/rest/v/feed/liked"
# 关注列表（POST JSON body：pcursor 翻页游标 + ftype=1 关注 / 2 粉丝；缺签名静默返回空列表，必须签名）
RELATION_FOL_URL = "https://www.kuaishou.com/rest/v/relation/fol"
# 博主主页作品列表（POST JSON body：user_id=博主 eid + pcursor 翻页游标，page 固定 "profile"）
PROFILE_FEED_URL = "https://www.kuaishou.com/rest/v/profile/feed"
# 收藏/取消收藏单视频（POST body：photoId + collect=1 收藏 / 2 取消；作者 userId 可选）
PHOTO_COLLECT_URL = "https://www.kuaishou.com/rest/v/photo/collect"
# 点赞/取消点赞单视频（POST body：photo_id + cancel=0 点赞 / 1 取消；作者 user_id、exp_tag 可选）
PHOTO_LIKE_URL = "https://www.kuaishou.com/rest/v/photo/like"

# 视频详情（POST /graphql，visionVideoDetail；graphql 不在 __NS_hxfalcon 签名白名单，
# 直连即可。查询文本从站点 short-video bundle 剥离，字段保留 parser 所需的最小集）
GRAPHQL_URL = "https://www.kuaishou.com/graphql"
VIDEO_DETAIL_QUERY = """query visionVideoDetail($photoId: String, $type: String, $page: String, $webPageArea: String) {
  visionVideoDetail(photoId: $photoId, type: $type, page: $page, webPageArea: $webPageArea) {
    status
    type
    author {
      id
      name
    }
    photo {
      id
      duration
      caption
      timestamp
      likeCount
      viewCount
      photoUrl
      photoH265Url
      manifest {
        adaptationSet {
          representation {
            url
            backupUrl
            qualityType
            qualityLabel
            width
            height
          }
        }
      }
      manifestH265
    }
  }
}"""

# __NS_hxfalcon 签名生成脚本（Node CLI，stdin JSON → stdout 签名）
SIG_SCRIPT = "sig4.cjs"

API_PAGE_COUNT = 18          # API 直连单页条数（服务端实测每页 18 条）
API_PAGE_INTERVAL_SEC = 0.8  # API 直连翻页间隔（防风控节流）
WRITE_INTERVAL_SEC = 0.5     # 批量写操作（点赞/收藏）逐条间隔（防风控节流）

# 翻页结束哨兵：末页 pcursor 返回 "no_more"
PCURSOR_NO_MORE = "no_more"

# 判定 API 直连登录态的 cookie（服务端会话，任一存在且非空即视为登录）
LOGIN_COOKIE_KEYS = ("kuaishou.server.webday7_st", "userId")

DEFAULT_COUNT = 0            # 不填 count 时抓全部（0 = 无上限）
MAX_COUNT = 500
