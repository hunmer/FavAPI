# web 数据模型（无数据库；类型 + 客户端状态）

## UI 类型（src/types.ts）

| 类型 | 说明 |
|------|------|
| `NavTab` | 7 值联合：dashboard/accounts/data/tasks/schedule/downloads/settings |
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

后端 snake_case 行类型（AccountRow/TaskRow/FavoriteRow/AgentConfigRow/ScheduleRow/PlatformInfoRow 等）在 `api.ts` 内定义，经 `toAccount/toTask/toScrapedItem/toSchedule` 等 `to*` 函数映射为上述 UI 类型——**组件层永远不见 snake_case**。

## App 级状态（App.tsx，无状态库）

- 服务端数据：accounts、tasks、scrapedItems（favorites limit 5000 全量拉到前端过滤）、schedules、agents、tagStats/tagGroups、stats。
- 运行态：streamingByAccount（SSE 流式抓取）、scrapingAccountIds、toast、3 个全局 Modal 开关。
- localStorage 持久化：theme、fullPage、avatar、平台操作表单值。

## 平台静态元数据（data/platforms.ts）

`PlatformMeta`：id/name/icon/color/badgeBg/isSupported/tagline/apiFetch?。静态 11 平台（含未实现的 zhihu/weibo/twitter），App 启动时按 GET /platforms 合并 isSupported 并动态追加未知平台。

## 遗留数据

`data/mockFavData.ts` 的 INITIAL_ACCOUNTS/MOCK_COOKIES/INITIAL_TASKS/INITIAL_SCRAPED_ITEMS/INITIAL_SCHEDULES 为早期 mock，现仅 PLATFORMS re-export 被 DataBrowserView/DataItemCard 引用，其余未使用。
