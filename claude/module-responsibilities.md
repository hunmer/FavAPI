# 模块职责

后端单一 Python 包 `app/` + 根 `platforms/` 声明式配置目录 + `web/` 前端（独立索引见 [web/CLAUDE.md](../web/CLAUDE.md)）。

## 顶层模块

| 模块 | 职责 |
|------|------|
| `app/config.py` | DATA_DIR/PLATFORMS_DIR/HOST/PORT/HEADLESS + 超时/并发常量 |
| `app/database.py` | 8 表 SCHEMA、`Database` 单例 `db`、老库迁移 `_migrate()` |
| `app/models.py` | Pydantic 请求/响应模型 |
| `app/server.py` | `create_app()` + lifespan（db/scheduler/download_worker）+ 挂 10 个 router |
| `app/taxonomy.py` | 内置标签分类体系（8 分组 60+ 中文标签），打标候选池 + 首启物化 tag_groups |
| `app/utils.py` | now_iso / new_id / 日期窗口三件套 |

## app/api（9 个路由文件，前缀 /api/v1）

| 文件 | 职责 |
|------|------|
| `accounts.py` | 账号 CRUD、扫码登录(202)、登录态检查、手动浏览窗口、cookies 快照、微信 JSON 上传、身份刷新（单个/批量）、B 站收藏夹编辑删除、平台 API 操作（同步+SSE）、`/platforms` 元信息与 reload 与图标 |
| `fetch.py` | `POST /fetch`（同步/异步）+ `POST /fetch/stream`（SSE） |
| `queries.py` | `/stats` 仪表盘统计、`/tasks`、`/favorites`（多维过滤+facets）、`/tags` 聚合、批量删收藏 |
| `schedules.py` | 定时计划 CRUD + 立即触发（防重入） |
| `downloads.py` | 下载队列：列表/入队(幂等)/重试/暂停/文件管理器定位/删除 |
| `settings.py` | settings.json 读写 + 控制台头像上传下发 |
| `tags.py` | 删标签、标签引用计数、标签分组 CRUD、手动打标 |
| `agents.py` | AI Agent（OpenAI 兼容配置）CRUD + 连通性测试 |
| `ai_tag.py` | `POST /ai/tag/stream` SSE 批量打标 |

## app/services（13 个模块）

| 文件 | 职责 |
|------|------|
| `browser.py` | Playwright 持久化 profile 会话（per-profile Lock + 全局 Semaphore）、手动浏览窗口、open_tab、cookie 判定 |
| `account_manager.py` | 账号 CRUD、登录防重入集合、cookie 快照、身份回填（头像落盘）、删号级联清理 |
| `task_executor.py` | 抓取校验 → 同步/异步/SSE 三种执行 → 入库 → friendly_error；ai_tag 分流 |
| `data_store.py` | contents upsert / favorites 写入与多维查询（json_each 标签匹配、发布日期 SQL）/ facets / 任务 CRUD / 标签统计 / 详情 URL 模板 |
| `tag_store.py` | 标签分组 CRUD、删标签（含联动）、手动打标（上限 10） |
| `scheduler.py` | 30s 循环扫描到期计划并触发（防重入、失败也推进 next_run_at） |
| `schedule_store.py` | schedules CRUD + croniter 校验/算下次运行时间 |
| `download_worker.py` | 2s 扫描队列，子进程跑 yt-dlp（可注入 cookie）/videodl，进度节流落库，取消杀进程 |
| `download_store.py` | downloads CRUD + 幂等入队 + 按平台模板生成原站 URL |
| `ai_tagging.py` | 批量 LLM 打标（批 20、超时 120s、json_object 降级重试）、SSE 版、agent 连通性测试 |
| `agent_store.py` | ai_agents 表 CRUD |
| `app_settings.py` | data/settings.json 读写（profile/headless/间隔/超时/下载目录/下载并发） |

## app/platforms

| 文件/目录 | 职责 |
|------|------|
| `base.py` | `BasePlatformAdapter` 抽象、`AccountContext`、`FetchResult`、`LoginExpiredError`、`ApiOperation`（写操作表单 schema：text/textarea/number/date/select） |
| `registry.py` | 注册表 + `load_declarative()` 声明式扫描；注册顺序：Python 平台 → 声明式 → 覆盖型 Python 平台 |
| `declarative.py` | `DeclarativeAdapter`：platform.json → 浏览器拦截抓取；支持 proxy auto/env、页面脚本钩子、子进程 Python 钩子（限平台目录内、30s 超时） |
| `douyin/` | 浏览器拦截 + curl_cffi API 直连；7 个写操作（取消收藏/点赞/稍后再看等） |
| `bilibili/` | 浏览器上下文内直连公开接口翻页；收藏夹编辑/删除、按日期窗口批量取消收藏 |
| `xiaohongshu/` | 浏览器拦截 + xhshow 签名 API 直连；8 个操作（收藏/点赞/批量取消等） |
| `kuaishou/` | 声明式抓取 + Node sig_vm.js 离线签名 API 直连（依赖系统 Node ≥16）；9 个操作 |
| `tiktok/` | 声明式抓取 + curl_cffi API 直连（msToken/X-Bogus 占位）；3 个操作 |
| `threads/` | 浏览器模式（HTML Relay preloader）+ GraphQL API 直连；2 个操作 |
| `youtube/` | 纯 Python：浏览器解析「喜欢的视频」播放列表 DOM；无 API 直连 |
| `wechat/` | JSON 文件导入（WeChatDataAnalysis 导出）；无需登录 |

## 根 platforms/ 目录（FAVAPI_PLATFORMS_DIR）

声明式平台配置：`kuaishou/platform.json`、`tiktok/platform.json`、`youtube/platform.json`、`threads/`（仅 favicon.ico）。同平台同时存在 Python 适配器时，后者覆盖注册。

## 其他根目录

| 路径 | 职责 |
|------|------|
| `tests/` | 7 个测试脚本（见 testing-and-quality.md） |
| `samples/` | 4 平台收藏接口响应样本 JSON（parser 单测对照） |
| `scripts/` | threads_saved_sample.json 抓包样本 |
| `docs/api-fetch-integration-guide.md` | API 直连模式接入指南（逆向→原型→落地→验证） |
| `verify_bili_*.py` | 3 个含真实 cookie 的临时人工验证脚本 |
| `PRD.md` / `pages.md` | 产品需求 / 前端页面规划 |
