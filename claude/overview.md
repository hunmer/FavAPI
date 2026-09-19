# 架构总览

## 定位

FavAPI 是本地/私有化部署的「个人收藏数据同步中台」：FastAPI + Playwright/HTTP 双通道抓取 9 个平台的个人收藏与点赞数据，多账号登录态管理，「特别关注」博主追踪体系，SQLite 持久化，附带 React SPA 管理控制台，并可打包为桌面便携应用（pywebview + PyInstaller + tufup 自动更新）。单用户本地服务，非公开爬虫。

## 分层结构

```
React SPA (web/, Vite 构建 → app/web/router.py 托管 web/dist)
        │  /api/v1 JSON + SSE
FastAPI HTTP API (app/api: 12 个路由文件)
        │
服务层 (app/services, 18 个模块)
  ├─ account_manager / browser       账号 + Playwright 会话（profile 锁 + 信号量）
  ├─ task_executor                   抓取任务生命周期（校验/同步/异步/SSE）
  ├─ data_store / tag_store / raw_store  contents/favorites/tags/原始响应持久化
  ├─ follow_store                    特别关注共享资产（头像/快照/封面/媒体代理路由）
  ├─ scheduler / schedule_store      cron 定时调度
  ├─ download_worker / download_store / aria2_service  yt-dlp/videodl/aria2c 下载队列
  ├─ ai_tagging / agent_store        LLM 批量打标（OpenAI 兼容接口）
  ├─ cover_worker / notification_store  封面本地化 / 应用内通知
  ├─ updater                         tufup 自动更新（仅 frozen 便携包）
  └─ app_settings                    settings.json 运行参数
        │
平台适配器 (app/platforms)
  ├─ base / registry / declarative   抽象基类 + 注册表 + JSON 声明式平台
  └─ 9 平台适配器（浏览器拦截 / API 直连 / JSON 导入三模式）
        │
SQLite (app/database.py, aiosqlite 单连接 + WAL, 10 表)
```

依赖方向自上而下单向；`platforms` 不 import `api`，适配器只依赖 `services.browser` 等少数服务。follows 体系的共享逻辑放 `services/follow_store.py`，供 api 层与各平台 adapter 双向复用（防 platforms 反向依赖 api）。

## 抓取的三种模式

| 模式 | 机制 | 代表平台 |
|------|------|----------|
| 浏览器拦截 | Playwright 打开收藏页滚动，`page.on('response')` 拦截 XHR | douyin、xiaohongshu、kuaishou/tiktok（声明式） |
| API 直连 | `fetch_favorites_api`：curl_cffi 模拟 TLS 指纹直接调平台接口 | douyin、xiaohongshu、kuaishou、tiktok、threads、instagram |
| 无浏览器请求 | 浏览器上下文内直接分页请求公开接口 | bilibili |
| JSON 导入 | 上传第三方导出文件解析入库 | wechat |

写操作（收藏/点赞/取消等）走 `api_operations` 体系：`POST /accounts/{id}/operations/{op_id}`，支持 SSE 流式执行。详见 `docs/api-fetch-integration-guide.md`。

特别关注（follows）是独立的第二抓取面：8 平台（除 wechat）实现 `follows_api_implemented`，链路为「账号关注列表 → 挑选博主 → 定期同步博主作品 → 未读数 → 播放/已读」，全部经 `/api/v1/follows/*` 路由与 `follow_store` 资产层。

## 声明式平台（declarative.py）

无需写 Python：根目录 `platforms/<name>/platform.json` 声明登录 cookie、响应拦截字段映射、页面脚本钩子，启动时 `registry.load_declarative()` 自动注册，运行中可 `POST /api/v1/platforms/reload` 热加载。Kuaishou/TikTok 以 Python 适配器继承 `DeclarativeAdapter` 叠加 API 直连后覆盖同名声明式注册。

## 运行时形态

- 入口 `main.py`：单实例锁（Windows 命名 Mutex / POSIX flock）→ uvicorn 跑 daemon 线程 → 可选 pywebview 窗口（macOS 要求主线程跑 UI）；frozen 包启动 tufup 后台更新检查，更新就绪回调优雅退出并重启。
- lifespan 启动顺序：`db.connect()` → `data_store.interrupt_stale_tasks()` + `download_store.requeue_stale_running()`（清启动残留）→ `scheduler.start()` → `download_worker.start()` → `cover_worker.start()`；关停逆序。
- 单 aiosqlite 共享连接（WAL），aiosqlite 内部单线程串行。
- 后台任务均为 `asyncio.create_task`（扫码登录、异步抓取、调度循环、下载扫描），无任务队列。
- 浏览器并发：per-profile asyncio Lock（同账号串行）+ 全局 Semaphore(2)。
- 下载为子进程（yt-dlp / videodl / aria2c 三选一），worker 2s 扫描队列，并发 1–3 可配。
- 发布：GitHub Actions（`.github/workflows/release.yml`）矩阵构建 Win/mac 便携包（PyInstaller + vite build + Chromium）。

## 关键设计取舍

| 取舍 | 理由 |
|------|------|
| aiosqlite 裸 SQL，不用 ORM | 单用户、schema 简单，减少抽象层 |
| 双抓取通道（浏览器 + API 直连） | 浏览器稳但慢；API 直连快但需对抗签名（curl_cffi 指纹 / xhshow / Node sig_vm） |
| 默认有头浏览器 | 抖音等对无头检测严格 |
| 声明式 JSON 平台 | 简单平台零 Python 代码；复杂平台仍写 Python 并可继承声明式 |
| 删账号级联删 favorites、contents 保留 | contents 跨账号去重，属全局数据；删除后跑 purge_orphan_contents 清孤儿 |
| follows 资产走文件系统而非入库 | 头像/作品快照/封面是可重建缓存，SQLite 只存 follow_authors/follow_reads 两张轻表 |
| ai_tag 复用 fetch_tasks 表 | 少一张表；`new_favorites` 列在打标场景复用为打标条数 |
| 前端用 HashRouter | 后端 StaticFiles 托管无 SPA 回退路由，hash 路由免后端配合 |
| 桌面化（pywebview/tufup）而非 Electron | 复用 Python 进程与登录态 profile；tufup 提供增量更新 |

## 数据流（一次抓取）

`POST /api/v1/fetch` → `task_executor.validate_fetch` → 建 fetch_tasks 行 → `adapter.fetch_favorites`（或 `fetch_favorites_api`）→ 日期窗口过滤 → `data_store.save_fetch_result`（upsert contents → insert-or-ignore favorites，favorites.source 记来源）→ 任务落库 → 自动刷 cookie 快照 → 返回 `result_count / new_favorites / cursor / has_more / items(≤100 摘要)`。SSE 版（`/fetch/stream`）增量 on_batch 入库。
