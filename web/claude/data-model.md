# web 数据模型（无数据库；类型 + 客户端状态）

## UI 类型（src/types.ts）

| 类型 | 说明 |
|------|------|
| `NavTab` | 8 值联合：dashboard/accounts/data/follows/tasks/schedule/downloads/settings |
| `PlatformId` | string（平台由后端动态提供，不写死联合类型） |
| `Account` | 含 ownerNickname/ownerAvatar/ownerUid（身份回填）、folders（B 站收藏夹）、isBrowserOpen |
| `AccountStatus` | active / expired / disabled / logging_in |
| `BilibiliFolder` | id/name/count/mediaId/isDefault/intro/cover |
| `TaskRecord` + `TaskStatus` + `OperationType` | 任务：running/success/failed；操作：增量抓取/全量抓取/登录态检查/会话续期/智能打标 |
| `ScrapedItem` | 收藏条目：title/url/author/duration/likes/favorites/folderName/favTime/crawlTime/coverUrl/tags/notes 等 |
| `ScrapingFormData` | 抓取表单：count/cursor/isAsync/method(browser\|api)/日期区间 + bilibili/xiaohongshu/wechat 专属字段 |
| `ScheduledSync` | cron/status(active\|paused)/action(list_favorites\|ai_tag) |
| `CookieItem`、`PrimaryTab` | cookie 查看；PrimaryTab 未见实际使用（疑似遗留） |

## 后端行类型与映射（api.ts）

后端 snake_case 行类型（AccountRow/TaskRow/FavoriteRow/AgentConfigRow/ScheduleRow/PlatformInfoRow/FollowAuthorRow/FollowingUserRow/FollowPostRow/PlayInfo/FollowSyncResult/FollowSyncProgress 等）在 `api.ts` 内定义，经 `toAccount/toTask/toScrapedItem/toSchedule` 等 `to*` 函数映射为上述 UI 类型——**组件层永远不见 snake_case**。

follows 专属：`FollowPostRow` 含 `url`/`read`（已读态）；`PlayInfo` 含 `music_url`（图文 BGM）/`iframe_url`（YouTube 嵌入）/`share_url`。

## App 级状态（App.tsx，无状态库）

- 服务端数据：accounts、tasks、scrapedItems（favorites limit 5000 全量拉到前端过滤）、schedules、agents、tagStats/tagGroups、stats。
- 运行态：streamingByAccount（SSE 流式抓取）、scrapingAccountIds、toast、全局 Modal 开关、follows 的 syncTick（一键同步完成后通知 FollowsView 刷未读数）。
- localStorage 持久化：theme、fullPage、avatar、平台操作表单值、视图模式（`favapi_data_filters`/`favapi_author_view_mode` 等键）。

## 平台静态元数据（data/platforms.ts）

`PlatformMeta`：id/name/icon/color/badgeBg/isSupported/tagline/apiFetch?/followsApi?/fetchTargets?。静态 12 平台（含未实现的 zhihu/weibo/twitter；instagram 已收录且 followsApi），App 启动时按 GET /platforms 合并 isSupported 并动态追加未知平台。

## 遗留数据

`data/mockFavData.ts` 的 INITIAL_*/MOCK_* 为早期 mock，现仅 PLATFORMS re-export 被引用，其余未使用。
