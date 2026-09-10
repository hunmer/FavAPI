# 架构总览

## 定位

FavAPI 是本地/私有化部署的「个人收藏数据同步中台」：FastAPI 服务 + Playwright 真实浏览器登录态，抓取各平台（当前抖音，Bilibili 占位）的个人收藏，持久化到 SQLite，并提供 Jinja2 Web 管理界面。单用户本地服务，非公开爬虫。

## 分层结构

```
Web 管理界面 (app/web, Jinja2 + 原生 JS, 数据全走 JSON API)
        │
FastAPI HTTP API (app/api: accounts / fetch / queries)
        │
服务层 (app/services)
  ├─ account_manager  账号 CRUD + 登录流程内存态
  ├─ task_executor    任务生命周期 + 校验 + 结果入库
  ├─ data_store       contents/favorites/fetch_tasks 持久化
  └─ browser          Playwright 会话（持久化 profile + 并发控制）
        │
平台适配器 (app/platforms)
  ├─ base / registry  抽象基类 + 注册表
  ├─ douyin           完整实现（扫码登录 / cookie 检查 / listcollection 拦截抓取）
  └─ bilibili         占位（NotImplementedError → API 层转友好提示）
        │
SQLite (app/database.py, aiosqlite 单连接 + WAL)
```

依赖方向自上而下单向；`platforms` 不 import `api`，`services` 被 `api` 与 `platforms`（仅 browser）共用。

## 运行时形态

- 单进程 uvicorn（`python main.py` 或 dev 热重载），默认 `127.0.0.1:8300`。
- lifespan 内建立/关闭唯一的 aiosqlite 连接（WAL 模式），所有请求共享；aiosqlite 内部单线程串行执行。
- 登录与抓取均在同一事件循环内以 `asyncio.create_task` 后台执行，不引入任务队列。
- 浏览器并发：每 profile 一把 asyncio Lock（同账号串行）+ 全局 Semaphore(2)。
- 登录防重入与「登录中」状态是纯内存态（`account_manager._login_in_progress`），服务重启即清空。

## 关键设计取舍

| 取舍 | 理由 |
|------|------|
| aiosqlite 裸 SQL，不用 ORM | 单用户、schema 固定（PRD 给定四表），减少抽象层 |
| 抓取默认同步等待，`async_run=true` 才后台执行 | 兼顾 PRD 示例（响应含数量）与长任务轮询 |
| 抖音抓取靠「页面滚动 + 响应拦截」而非直接调 API | 页面内接口带签名，浏览器上下文内拦截最稳 |
| 默认有头浏览器（HEADLESS=0） | 抖音对无头检测严格；仅登录态检查固定无头（不导航页面，只读 cookie） |
| 删除账号时 favorites 级联删、contents 保留 | contents 跨账号去重，属全局数据 |
| Bilibili 用 `implemented=False` 占位而非不注册 | 页面下拉框/错误提示统一由注册表元信息驱动 |

## 数据流（一次抓取）

`POST /api/v1/fetch` → `task_executor.start_fetch`（校验账号/平台/action）→ 建 `fetch_tasks` 行 → `adapter.fetch_favorites`（开浏览器、滚动、拦截响应、parser 转通用行）→ `data_store.save_fetch_result`（upsert contents → insert-or-ignore favorites）→ 更新任务状态 → 返回 `result_count / new_favorites / cursor / has_more / items(前100条摘要)`。
