# Handoff：特别关注（follows）体系多平台接入指南

> 写给下一个 agent：把一个新平台（快手/小红书/TikTok/Threads…）接入特别关注体系。
> 本文档 2026-09-19 基于 douyin + bilibili 双平台已落地的实现整理，全部代码已验证可用。
> 深层原理与抓包方法见 `docs/api-fetch-integration-guide.md`（尤其第 3 节四步接入流程），
> 本文只讲 follows 体系的增量部分，不重复其内容。

## 1. 体系现状

follows 是与「抓取/操作」平行的第三条通道（路由 `app/api/follows.py`，前缀 `/api/v1/follows`）：
关注列表拉取 → 添加特别关注博主（`follow_authors` 表，主键 sec_uid = 平台博主 ID）→
博主主页作品浏览 → 播放器（已读标记）→ 一键同步最新作品入库（`favorites.source='特别关注'`）。

2026-09-19 已完成平台解耦：**follows.py 零平台依赖**，全部按账号/博主的 `platform`
字段经 `registry.get_adapter()` 分发到 adapter 的 `follows_*` 能力方法。
已接入：douyin（原有逻辑包装）、bilibili（新增）。未提交的改动见 `git status`
（涉及 base/registry/follow_store/follows.py + 两平台 adapter + 前端 6 文件）。

## 2. 架构与数据流

```
前端 FollowsView / AuthorPage / PlayerModal / FollowingList(账号详情 Tab)
        │  /api/v1/follows/**
        ▼
app/api/follows.py  ──按 platform──▶  registry.get_adapter(platform)
        │                                      │
        │  统一 cursor 语义 / 统一条目结构        ▼
        │                            adapter.follows_*（能力方法，base.py 定义）
        │                                      │
        │                                      ▼
        │                          平台 api_client.py（curl_cffi 直连，同步函数）
        ▼
data_store.save_fetch_result(account, items, source="特别关注")   ← 同步入库，平台无关
```

媒体播放统一走 `GET /follows/media?url=...` 流式代理（域白名单 + Range 透传），
头像本地化到 `data/follow_avatars/{sec_uid}.{ext}`（`app/services/follow_store.py`）。

## 3. 接口契约（adapter 必须实现的 7 个点）

定义在 `app/platforms/base.py` 的 `BasePlatformAdapter`（全部有默认 NotImplementedError，
签名和 docstring 以源码为准）：

| 成员 | 签名要点 | 语义约定 |
|---|---|---|
| `follows_api_implemented` | 类属性 = True | 能力声明；registry `_info` 下发给前端 |
| `follows_profile_cookie` | `async (account) -> str` | 取登录 cookie 头；失效抛 `LoginExpiredError`（执行器会标记账号 expired） |
| `follows_self_uid` | `(cookie_header) -> str` | 当前账号的博主主键；空串 = 提取失败（API 层转 400） |
| `follows_validate_uid` | `(sec_uid) -> None` | 主键格式校验，不合法抛 ValueError（转 400）；可不覆写 |
| `follows_fetch_following` | `async (cookie, self_uid, count=0, on_batch=None) -> (list, bool)` | 条目统一结构见下；count 0 = 全部 |
| `follows_fetch_posts_page` | `async (cookie, sec_uid, cursor=0, count=18) -> dict` | **cursor：0 = 首页，响应 cursor 供下次翻页，末页必须返回 0** |
| `follows_play_info` | `async (cookie, content_id) -> dict` | PlayerModal 统一结构见下 |
| `sync_author_posts` | `async (account, author_row, cookie, count) -> list` | 拉 count 条通用 content 行 + 回填 `last_synced_at`/uid/昵称/头像；**不负责入库** |

**统一数据结构**（前端 `web/src/api.ts` 的 `FollowingUserRow` / `PlayInfo` / `FollowPostRow` 是契约的消费端）：

- followings 条目：`{sec_uid, uid, unique_id, nickname, signature, avatar_url, follower_count, aweme_count, is_top}`，平台缺失字段置 None/空串
- play_info：`{aweme_id, desc, create_time(epoch 秒), duration, statistics(键：digg_count/comment_count/collect_count/share_count + 平台附加), author:{nickname, sec_uid}, video_urls: string[], images: [{url,...}], music_url?}`
- posts_page 的 items = 通用 content 行（parser 输出：content_id/title/cover_url/duration/author_id/author_name/statistics/raw_data/collected_at），其中 `collected_at` 语义 = **发布时间**（follows.py 直接下发为 published_at）
- duration 单位不统一是历史遗留：douyin 毫秒、bilibili 秒，前端 `fmtMs` 按数量级（>10000 视为毫秒）归一，新平台任选但别落在歧义区（几千秒的长视频会误判，尽量给秒）

## 4. 新平台接入清单（按序做）

参照模板：`app/platforms/bilibili/adapter.py` 的「特别关注（follows）体系」段落
+ `app/platforms/bilibili/api_client.py` 末尾两个翻页函数。

1. **api_client.py**：实现单页函数（同步，curl_cffi `impersonate="chrome"`，`asyncio.to_thread` 包装由 adapter 做）
   + async 翻页循环（`API_PAGE_INTERVAL_SEC` 节流，count=0 全量）。翻页语义两种：偏移页码（bilibili pn）或服务端游标（douyin max_cursor），adapter 层负责归一到统一 cursor 语义。
2. **parser.py**：响应 → 统一结构 / content 行。参考 `bilibili/parser.py::parse_following_list / parse_arc_search`。
3. **adapter.py**：类属性 `follows_api_implemented = True` + 实现 7 个点。`follows_play_info` 注意：**播放直链必须是「客户端可独立访问」的 URL**（见第 5 节坑 1）。
4. **follow_store.py**：平台媒体/头像/封面 CDN 域名加入 `MEDIA_HOST_SUFFIXES`；若该平台 CDN 需要站内 referer，同时把域名加进 `_DOUYIN_REFERER_SUFFIXES` 风格的判断（现为抖音专用列表，可自行扩展成 per-platform 映射）。
5. **前端 `web/src/data/platforms.ts`**：该平台条目加 `followsApi: true`（控制账号详情「关注列表」Tab 是否出现）。其余组件零改动。
6. **验证**（见第 6 节）。

不动的东西：`follows.py`、`FollowsView/AuthorPage/PlayerModal/FollowingList`、
`registry.py`（已通用）、`base.py`（除非扩展契约）。
另外注意：若新平台在 douyin adapter 有 `follow_sync` 类似的 task 体系抓取目标，
记得该查询按 `WHERE platform = ?` 过滤（douyin 已改，别的平台抄这个模式）。

## 5. 踩坑记录（全部实测，别再踩）

1. **登录态下发的播放直链可能绑定会话**：bilibili 登录态 playurl 返回 bcache 个性化
   CDN 链接（query 带 mid/uipk），换任何客户端（媒体代理/aria2/带 cookie 的 curl_cffi）一律
   403；匿名解析的直链仅 UA 即可播。所以 bilibili `follows_play_info` **固定匿名解析**
   （720P 封顶，播放场景够用；高画质走下载通道的 DASH）。新平台接入时先验证：
   play_info 拿到的直链，用裸 UA curl 一发 206/200 才算数。
2. **playurl/view 跨域 referer**：api.bilibili.com 是跨域接口，浏览器只发根 origin，
   手动带视频页完整 referer 反而 412（风控）；space 系接口带完整 space referer 没问题。
3. **WBI 签名**：`space/wbi/arc/search` 需要 WBI 签名，mixin key 取自 nav 的 `wbi_img`
   （匿名可取，`code=-101` 但密钥照常下发，勿当错误）。bilibili 侧已有现成实现
   `api_client._wbi_mixin_key / _wbi_sign` 直接复用。
4. **翻页 cursor 归一**：douyin max_cursor 是时间戳（末页 0），bilibili 是页码。
   adapter 层换算（bilibili：入参 cursor=已翻页数 → pn=cursor+1；末页 cursor 归 0），
   前端 `loadPage(cursor)` 逻辑两平台通吃，新平台照此换算。
5. **平台一致性**：follows.py 已加校验（浏览/同步账号 platform ≠ 博主 platform → 400），
   新平台无需重复实现，但要保证 `follow_authors.platform` 写入正确（前端 FollowingList
   添加时传 `platform: account.platform`，后端 `FollowAuthorCreate.platform` 默认 douyin）。
6. **cookie 获取成本**：`follows_profile_cookie` 通常起一次无头 Chromium 读 profile
   （`browser.session` 有同 profile 串行锁）。翻页循环里复用一次 cookie，别每页取。
7. **同步去重**：`save_fetch_result` 按 (account, platform, content_id) 幂等，
   `sync_author_posts` 里 `items[:count]` 截断保证入库量与配置一致。
8. **同步回填**：UPDATE follow_authors 用 `COALESCE(NULLIF(?,''), col)` 模式，
   只在拿到非空值时覆盖；头像本地文件缺失时按库中 URL 补下（自愈）。
9. **平台接口下发 http 链接**：B 站投稿封面 `pic` 常为 `http://i1.hdslb.com/...`
   （头像 face 是 https）。`is_allowed_media_url` 已放行 http（域名白名单不变），
   实际上游请求经 `upgrade_media_url` 统一升 https；parser 侧新数据直接归一。
   新平台接入时留意接口下发的 scheme，别只测 https 样本。

## 6. 验证步骤（HTTP 层，服务 8300）

```bash
# 0. 平台元数据：目标平台应出现 "follows_api_implemented": true
curl -s http://127.0.0.1:8300/api/v1/platforms | python3 -m json.tool | grep -A1 follows

ACC=<平台账号 id>; SEC=<测试博主主键>
# 1. 关注列表（统一结构，total/has_more/followings）
curl -s "http://127.0.0.1:8300/api/v1/follows/following/$ACC?count=5"
# 2. 非法主键 → 400
curl -s -X POST .../follows/authors -d '{"sec_uid":"!!","platform":"<id>"}'
# 3. 添加博主 + 主页作品（cursor 翻两页验证归一语义）
curl -s -X POST .../follows/authors -d '{"sec_uid":"'$SEC'","platform":"<id>","account_id":"'$ACC'",...}'
curl -s ".../follows/authors/$SEC/posts?account_id=$ACC&count=5"
# 4. 同步入库（new 计数；重复跑 new=0）
curl -s -X POST .../follows/sync -d '{"sec_uids":["'$SEC'"],"count":3}'
# 5. 播放信息 + 媒体代理（直链必须 206，坑 1）
curl -s ".../follows/aweme/<作品ID>?account_id=$ACC"
curl -o /dev/null -w "%{http_code}" -H "Range: bytes=0-65535" ".../follows/media?url=<直链URL编码>"
# 6. 回归：douyin 已有博主的作品页/同步不受影响；不支持平台 400
```

前端：账号详情出现「关注列表」Tab → 拉取添加 → 特别关注页有平台徽标 →
博主主页（自动选同平台账号）→ 点卡片播放 + 自动已读 → Header 一键更新。

## 7. 关键文件索引

| 文件 | 角色 |
|---|---|
| `app/platforms/base.py` | follows_* 契约定义（含各方法 docstring 的结构约定） |
| `app/api/follows.py` | 平台无关路由层 + `_adapter_or_400` / `_account_cookie` 分发辅助 |
| `app/platforms/bilibili/adapter.py` | follows 完整实现模板（含 bcache 匿名解析注释） |
| `app/platforms/douyin/adapter.py` | 薄委托模板 + `follow_sync` 的 platform 过滤写法 |
| `app/platforms/bilibili/api_client.py` | 单页 + async 翻页循环模板（WBI 签名复用） |
| `app/platforms/bilibili/parser.py` | 统一结构解析模板（following / arc_search） |
| `app/services/follow_store.py` | 媒体白名单 / referer 策略 / 头像本地化 |
| `web/src/api.ts` 1076 行起 | 前端契约（类型即接口） |
| `web/src/data/platforms.ts` | `followsApi: true` 开关 |
| `docs/api-fetch-integration-guide.md` | 抓包/逆向/直连通用方法（第 3、8 节） |

## 8. Suggested skills

- `mattpocock-skills:implement`：按本文档清单逐条实现新平台接入。
- `mattpocock-skills:diagnosing-bugs`：直链 403 / 空响应 / 翻页异常时定位（先看第 5 节坑表）。
- `mattpocock-skills:research`：需要查目标平台接口的公开资料时。

## 9. 未尽事项 / 后续优化

- B 站关注列表接口不返回粉丝数（卡片显示「— 粉丝」），可从 relation 接口补。
- 投稿列表仅 pubdate 排序，可加「最多播放」（`order=click`，bilibili 已支持参数）。
- 抖音之外的 `follow_sync` task 抓取目标尚未在各平台声明（bilibili 可加同款）。
- `_DOUYIN_REFERER_SUFFIXES` 是列表写死的；平台多了可重构为 per-platform referer 策略表。

---
*敏感信息说明：本文档不含任何 cookie / 凭据。测试用 mid（如 517327498 罗翔说刑法）
为公开空间页数据。会话中出现过的一组登录 cookie 已过期性失效，未落盘到任何项目文件。*
