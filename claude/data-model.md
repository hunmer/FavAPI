# 数据模型

## SQLite（app/database.py；`data/favapi.db`，aiosqlite 单连接 + WAL，10 表）

### accounts — 账号
`account_id PK`（acc_ 前缀）、platform、name、status(active/expired/disabled)、profile_path、last_login_at、last_used_at、created_at、`extra JSON`（cookies 快照、各平台 owner 身份、B 站收藏夹缓存等）。

### fetch_tasks — 任务（抓取与 AI 打标共用）
`task_id PK`、account_id、platform、action、`request_params JSON`、status(pending/running/success/failed)、result_count、`new_favorites`（打标场景复用为打标条数）、error_message(截 2000)、started_at、finished_at。

### contents — 内容主表（跨账号共享，删账号保留）
`content_id PK` + `UNIQUE(platform, content_id)`、platform、account_id(最后抓取者)、title、description、author_id、author_name、cover_url、duration(ms)、`statistics JSON`、`raw_data JSON`（原始接口行）、first_seen_at / last_seen_at、`tags JSON 数组字符串`、tagged_at。

### favorites — 收藏关系
自增 id PK、account_id、platform、content_id、fav_media_id（B 站同视频多收藏夹场景）、fav_title、`source`（来源维度，空='收藏列表'，特别关注同步写'特别关注'）、collected_at（平台侧时间）、fetched_at、`UNIQUE(account_id, platform, content_id, fav_media_id)`。查询分组统计用 `COALESCE(NULLIF(source,''),'收藏列表')`。

### ai_agents — LLM 配置
agent_id PK、name、base_url、api_key、model_id、created_at。

### tag_groups — 标签分组
group_name PK、`tags JSON`（空库启动时物化 taxonomy.BUILTIN_TAG_GROUPS）。

### schedules — 定时计划
schedule_id PK、title、account_id（ai_tag 计划可空）、platform（可空=全平台）、action(list_favorites/ai_tag)、`params JSON`、cron_expr(5 段)、status(active/paused)、last_run_at、next_run_at、last_task_id、created_at。

### downloads — 下载队列
download_id PK、platform、content_id、account_id、title、url、downloader(yt-dlp/videodl/aria2c)、status(pending/running/success/failed/canceled/paused)、progress、output_path、error_message、created_at、started_at、finished_at。

### follow_authors — 特别关注博主（2026-09-19 新增）
sec_uid PK（抖音系 sec_uid，Instagram 为 username）、platform、account_id（经哪个账号浏览/同步）、uid、nickname、avatar、group_name、粉丝数、last_synced_at、created_at 等。

### follow_reads — 特别关注已读记录（2026-09-19 新增）
content_id PK、read_at。未读数 = follow_authors 关联 contents（author_id）减去 follow_reads。

索引：favorites(account_id,platform)、tasks(started_at DESC)、contents(platform)、schedules(status,next_run_at)、downloads(created_at DESC)、follow_authors(platform)、follow_reads(content_id)。`_migrate()` 处理老库加列/重建。

## follows 文件资产（follow_store.py，可重建缓存不入库）

| 路径 | 内容 |
|------|------|
| `data/follow_avatars/{sec_uid}.{ext}` | 博主本地化头像 |
| `data/follow_posts/{sec_uid}.json` | 博主作品快照（原子写合并） |
| `data/follow_covers/{platform}/{content_id}.{ext}` | 作品缩略图 |

删除博主时联动清理以上资产。

## 写入策略

抓取成功 → 逐条 upsert contents（ON CONFLICT(platform,content_id) 更新、保留 first_seen_at）→ INSERT OR IGNORE favorites → COUNT 差值即 new_favorites。详情 URL 由 `data_store._CONTENT_URL_TEMPLATES` 按平台模板生成（tiktok/threads 从 raw_data 拼）。

## 查询要点（data_store.list_favorites）

- tag 过滤：`json_each(contents.tags)` 精确匹配；`tags` 参数逗号分隔 OR。
- 发布日期过滤：SQL 内联函数把 raw_data 的 create_time/ctime/createTime(epoch) 转 date 比较。
- q 模糊：标题/作者/标签 LIKE。
- 收藏时间过滤（date_from/date_to）在 Python 侧 `utils.filter_by_date_window`。

## Pydantic 模型（app/models.py）

AccountCreate/Update/Out（avatar 统一字段）、FetchRequest、FetchItemSummary、TaskOut、ScheduleCreate（ai_tag 可空账号）/Update/Out、FavoriteItem（fav_media_id/fav_title/url/tags/tagged_at）、DownloadCreate（url 空则按模板生成）/Out、AgentCreate/Update/Out。

## 内存态（重启丢失）

| 位置 | 内容 |
|------|------|
| `account_manager._login_in_progress` | 登录中账号集合（409 防重入 + 前端「登录中」） |
| `browser._locks` / `_semaphore` | per-profile 锁 / 全局 2 并发；`is_busy()` 供 status 快速返回 |
| `follow_store._media_cookie_map` | TikTok URL 级会话 cookie 登记表（FIFO 上限 256） |
| `follow_store._tiktok_cookie_cache` | TikTok 匿名首页 cookie TTL 缓存 |
| `ai_tagging` 批次上下文 | SSE 断开判定 |
| `/stats` 目录体积缓存 300s | 避免频繁遍历磁盘 |

## 适配器数据结构（platforms/base.py）

- `AccountContext`：account_id / platform / name / profile_path。
- `FetchResult`：items（通用 content 行 dict）/ cursor / has_more / total / meta。
- `ApiOperation` + `ApiOperationParam`：写操作声明（op_id/params 表单 schema/danger 标记），前端自动渲染表单。
- `LoginExpiredError`：任务 failed + 账号标 expired。

## 标签体系（taxonomy.py）

`BUILTIN_TAG_GROUPS` 8 分组约 60+ 中文标签：打标 prompt 候选池（库内 top 120 优先）、前端分组展示、首启物化进 tag_groups。
