# 数据模型

## SQLite（aiosqlite 单连接，WAL；schema 见 app/database.py，源自 PRD 2.3）

### accounts — 账号 / Session

| 列 | 类型 | 说明 |
|----|------|------|
| account_id | TEXT PK | `acc_` + 8 位 hex |
| platform | TEXT | douyin / bilibili |
| name | TEXT | 默认「{平台名}账号」 |
| status | TEXT | active / expired / disabled（登录态检查与抓取会自动改写） |
| profile_path | TEXT | `data/profiles/{platform}_{account_id}`，创建后不可变 |
| last_login_at / last_used_at / created_at | TEXT | ISO 本地时间（utils.now_iso） |
| extra | TEXT | JSON 字符串 |

### fetch_tasks — 抓取任务

| 列 | 类型 | 说明 |
|----|------|------|
| task_id | TEXT PK | `task_` + 8 位 hex |
| account_id / platform / action | TEXT | action 如 list_favorites |
| request_params | TEXT | JSON |
| status | TEXT | pending → running → success / failed |
| result_count | INTEGER | 本次抓到条数 |
| error_message | TEXT | 截断 2000 字符 |
| started_at / finished_at | TEXT | |

### contents — 内容主表（跨账号共享，删除账号时保留）

| 列 | 类型 | 说明 |
|----|------|------|
| content_id | TEXT PK 组成 | 平台内容 ID（aweme_id / bvid），UNIQUE(platform, content_id) |
| platform / account_id | TEXT | account_id 为最后抓取者（upsert 覆盖） |
| title / description / author_id / author_name / cover_url | TEXT | title 取 desc 首行前 120 字 |
| duration | INTEGER | 毫秒 |
| statistics | TEXT | JSON：digg/comment/share/collect/play_count |
| raw_data | TEXT | 原始完整 JSON |
| first_seen_at / last_seen_at | TEXT | upsert 时保留 first_seen_at |

### favorites — 收藏关系

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK 自增 | |
| account_id + platform + content_id | UNIQUE | 重复抓取 INSERT OR IGNORE 去重 |
| collected_at | TEXT | 平台侧收藏时间（parser 从 collect_time/collected_at/collect_date 多字段尝试） |
| fetched_at | TEXT | 本服务抓取时间 |

索引：`idx_favorites_account(account_id, platform)`、`idx_tasks_started(started_at DESC)`、`idx_contents_platform(platform)`。

## 写入策略（data_store.save_fetch_result）

抓取成功 → 先逐条 upsert contents（ON CONFLICT 更新除 first_seen_at 外全部列）→ 再 INSERT OR IGNORE favorites → 前后 COUNT 差值即 `new_favorites`。

## Pydantic 模型（app/models.py）

- `AccountCreate`（platform, name, extra）/ `AccountUpdate`（仅 name、status 可改）/ `AccountOut`。
- `FetchRequest`（platform, account_id, action, params, async_run）。
- `TaskOut`、`FavoriteItem`（含服务端拼的 `url`：`https://www.douyin.com/video/{id}` 等）、`FetchItemSummary`。

## 内存态（不落库，重启丢失）

| 位置 | 内容 |
|------|------|
| `account_manager._login_in_progress` | 正在扫码登录的账号集合（409 防重入 + 页面「登录中」标记） |
| `browser._locks` / `browser._semaphore` | per-profile 串行锁 / 全局并发信号量；`is_busy()` 供 status 接口快速返回 |

## 适配器数据结构（platforms/base.py）

- `AccountContext`：account_id / platform / name / profile_path（服务层从 accounts 行构造）。
- `FetchResult`：items（通用 content 行 dict 列表）/ cursor / has_more / total。
- `LoginExpiredError`：抓取中检测到未登录 → 任务 failed + 账号标 expired。
