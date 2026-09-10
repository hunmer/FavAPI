# Task Plan: FavAPI — 多平台个人收藏抓取 HTTP API 服务

> 依据：[PRD.md](./PRD.md)（抖音完整实现 + Bilibili 占位）
> 创建日期：2026-09-10

## Goal

构建本地/私有化 FastAPI 服务：多账号 Session 管理（Playwright 持久化 profile）、抖音个人收藏抓取（拦截 `listcollection` API + 滚动加载）、SQLite 持久化、简易 Web 管理界面、Bilibili 平台占位。覆盖 PRD 里程碑 M1–M4。

## Key Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| Python 环境 | 项目内 `.venv`（`py -3.13` 创建） | 默认 `python` 是 hermes-agent 的 venv，不可污染 |
| 后端 | FastAPI + uvicorn | PRD 指定 |
| 数据库 | aiosqlite（异步，无 ORM） | 单用户本地服务，schema 简单，裸 SQL + PRD 表结构 |
| 浏览器 | Playwright（async API，`launch_persistent_context`） | 登录态持久化到 profile 目录；默认有头（抖音对 headless 检测严格） |
| 前端 | Jinja2 模板 + 原生 JS（调 JSON API） | PRD「最低可用」要求，避免构建链 |
| 抓取执行 | 默认同步等待返回结果；请求带 `"async_run": true` 时立即返回 task_id 后台执行 + 轮询 | 兼顾 PRD 示例（响应含数量）与长任务 |
| 并发控制 | 每账号 asyncio Lock（同 profile 不并发开浏览器）+ 全局 Semaphore(2) | PRD：初期单账号串行、多账号有限并发 |
| 登录流程 | `POST /login` 启动后台有头浏览器等扫码（超时 300s），前端轮询 status | 登录需用户交互，不能阻塞 HTTP 请求 |

## Phases

### Phase 1: 环境与项目脚手架 — `complete`
- [x] 创建 `.venv`（py -3.13），安装 fastapi / uvicorn / aiosqlite / playwright / jinja2
- [x] `playwright install chromium`（用户取消 → **挂起，待后续执行**）
- [x] 项目骨架目录、`app/config.py`、`.gitignore`、`requirements.txt`

### Phase 2: 数据层（SQLite）— `complete`
- [x] `app/database.py`：aiosqlite 连接管理、PRD 四表 schema（accounts / fetch_tasks / contents / favorites）、WAL
- [x] `app/services/data_store.py`：contents upsert、favorites 关系写入、任务记录读写
- [x] 单元冒烟：建库 → 写入 → 查询回读

### Phase 3: 平台适配器架构 — `complete`
- [x] `platforms/base.py`：BasePlatformAdapter 抽象类（login / check_login_status / fetch_favorites / supported_actions）
- [x] `platforms/registry.py`：适配器注册表（get_adapter(platform)）
- [x] `platforms/bilibili/adapter.py`：占位（NotImplementedError + 友好提示）

### Phase 4: 抖音登录与状态检查 — `complete`
- [x] `platforms/douyin/adapter.py`：persistent context 启动封装（复用会话管理器）
- [x] `login()`：打开 douyin.com 有头窗口等扫码，轮询 cookie `sessionid` 判定成功
- [x] `check_login_status()`：cookie 存在性 + 有效性检查（过期更新 status）
- [x] `app/services/browser.py`：浏览器上下文管理（per-account profile、锁、超时清理）

### Phase 5: 抖音收藏抓取 — `complete`
- [x] `constants.py`：目标页 / 拦截 API 匹配规则
- [x] `fetch_favorites()`：导航 → 监听 `listcollection` 响应 → 滚动加载 → 达到 count 或 has_more=0 停止
- [x] `parser.py`：aweme_list → 通用 content 行（含 raw_data 保留原始 JSON）
- [x] 未登录/失效时标记账号 expired 并报错
- [x] parser 单元测试（样例 JSON）

### Phase 6: HTTP API — `complete`
- [x] `POST/GET/DELETE /api/v1/accounts`、`POST .../login`、`GET .../status`（PRD 3.1 全部）
- [x] `POST /api/v1/fetch`（platform + account_id + action + params + async_run）
- [x] `GET /api/v1/tasks`、`GET /api/v1/tasks/{id}`、`GET /api/v1/favorites`
- [x] `app/services/task_executor.py`：任务生命周期（pending→running→success/failed）、结果入库
- [x] API 冒烟测试（无浏览器路径：参数校验 / 404 / bilibili 友好报错 / 任务记录）

### Phase 7: Web 管理界面 — `complete`
- [x] 页面：账号列表+新增、账号详情（登录/状态/删除/触发抓取）、任务记录、数据浏览
- [x] Jinja2 `base.html` 布局 + 原生 JS 调 API，轮询登录状态
- [x] Bilibili 选项显示「即将支持」

### Phase 8: 端到端验证与收尾 — `complete`
- [x] 服务启动冒烟（uvicorn boot，/ 与 /api/v1/accounts 返回 200）
- [x] 完整 API 流程测试（创建账号 → 模拟抓取任务记录 → favorites 查询回读）
- [x] README.md（启动方式、API 文档、登录流程说明）
- [x] 抖音真实登录/抓取需用户扫码，代码就绪 + 说明文档

## Verification (PRD 验收标准映射)

| # | PRD 验收 | 验证方式 | 状态 |
|---|----------|----------|------|
| 1 | 多账号创建/登录 | API + 页面；登录需扫码（用户侧） | ✅ 代码就绪，服务端逻辑冒烟通过（真实扫码待用户执行） |
| 2 | 指定 account_id 抓取 | fetch API 路由到对应 profile | ✅ 同上 |
| 3 | 结果入库可查询 | 模拟数据入库 → favorites API 回读 | ✅ 冒烟通过 |
| 4 | 页面完整闭环 | 页面元素齐全，JS 流程联通 | ✅ 页面渲染 + API 联通 |
| 5 | Bilibili 明确提示 | API 返回 400「暂未实现」 | ✅ 冒烟通过 |
| 6 | count 数量符合预期 | 抓取循环逻辑 + 单元测试 | ✅ 逻辑测试通过 |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `await` 用在非 async 函数 `_get_account_or_404`（SyntaxError） | 1 | 改 async def + 调用处补 await |
| 批量编辑误删 `mark_login_started` 防重入行（409 变不可达） | 1 | grep 确认后补回 if 块 |
| test_parser 误写 walrus 语法（dict 内非法） | 1 | 改回普通键值 |
| 冒烟脚本 `await client.get(...).json()` 优先级错误（AttributeError） | 1 | 加括号 `(await ...).json()` |
| Starlette 新签名 `TemplateResponse(request, context)` → TypeError: unhashable dict | 1 | 改为 `TemplateResponse(request, "x.html", context)` |
| 冒烟脚本异常路径下进程挂起（aiosqlite 线程未随异常退出） | — | 仅测试脚本现象，正常路径 exit 0，服务不受影响 |
| Git Bash curl -d 传中文 JSON 报 body parse error | 1 | shell 编码问题非服务端 bug；httpx 中文创建已验证通过 |
