# FavAPI — 多平台个人收藏抓取 HTTP API 服务

本地/私有化部署的「个人收藏数据同步中台」：通过真实浏览器登录态或 API 直连抓取各平台个人收藏，支持多账号管理、定时同步、内容下载与 AI 打标，结果持久化到 SQLite，自带 Web 控制台，可一键打包为免安装便携版。

## 功能

- **多平台适配**：抖音、快手、Bilibili、小红书、TikTok、YouTube、Threads、微信收藏导入（JSON），另支持 `platform.json` 声明式平台热加载（无需写代码，见 `platforms/`）
- **多账号 Session 管理**：每账号独立浏览器 profile（登录态持久化），有头扫码登录、状态检查、禁用/删除
- **HTTP API 抓取**：`POST /api/v1/fetch` 统一入口，同步流式 / 异步轮询两种模式，`cursor` 增量翻页
- **定时同步调度**：cron 表达式配置周期任务，自动抓取收藏
- **内容下载**：视频/图片下载队列，后台工作器执行
- **AI 打标**：接入 AI Agent 对收藏内容自动生成标签
- **SQLite 持久化**：accounts / fetch_tasks / contents / favorites 等，重复抓取自动去重
- **Web 管理界面**：React 19 + Vite + Tailwind 4，覆盖账号、登录、抓取、任务、数据、调度、下载、设置（见 [web/README.md](./web/README.md)）
- **便携包**：PyInstaller 打包 + pywebview 原生窗口，双击即用，无需 Python 环境

## 快速开始（源码运行）

```bash
# 1. 创建虚拟环境并安装依赖（Python >= 3.12）
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # macOS / Linux
# py -3.13 -m venv .venv ; .venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows

# 2. 安装浏览器内核（首次必须，约几分钟）
.venv/bin/python -m playwright install chromium    # Windows: .venv/Scripts/python.exe -m playwright install chromium

# 3. 构建前端（生产模式由 FastAPI 托管 web/dist；开发模式可跳过用 npm run dev）
cd web && npm install && npm run build && cd ..

# 4. 启动服务（默认 http://127.0.0.1:8300）
.venv/bin/python main.py
```

打开 [http://127.0.0.1:8300](http://127.0.0.1:8300) 进入控制台，或 `/docs` 查看 API 文档。

### 使用流程（闭环）

1. 页面「账号」→ 选择平台 → 填名称 → 创建账号
2. 点击「登录」→ 弹出浏览器窗口 → App 扫码 → 页面自动轮询显示登录结果
3. 进入账号详情 → 填 count → 「开始抓取」（浏览器平台会打开窗口自动滚动加载，请勿关闭）
4. 页面「数据」查看收藏；「任务」查看执行历史；「调度」配置定时同步

### 外部依赖说明

| 依赖 | 用途 | 缺失时表现 |
|------|------|-----------|
| Node.js ≥ 16 | 快手签名脚本（`sig4.cjs`）离线生成 | 调用快手 API 直连抓取时报错并提示安装指引 |
| Playwright Chromium | 浏览器类平台的登录与抓取 | 报错提示执行 `playwright install chromium` |
| Node.js / npm | 仅 Web 前端开发与构建（`web/`） | 源码运行需先 `npm run build` 产出 `web/dist` |

## 便携包（PyInstaller）

```bash
bash scripts/build_portable.sh    # 产物：dist/FavAPI/（含 chromium 内核与平台资源，约 550MB）
```

- **双击 `FavAPI` 直接弹出原生窗口**（pywebview / macOS WKWebView）承载 Web 控制台，关闭窗口即优雅退出（停调度器与下载工作器后落盘）
- `FAVAPI_NO_WINDOW=1 ./FavAPI` 退回纯服务模式（行为同 `python main.py`）
- 便携包自带 Chromium（`pw-browsers/`），不依赖用户机器的浏览器缓存；`data/`、`platforms/` 均在包目录内，整目录拷走即用
- 便携包内仍需系统 Node.js（快手功能）；macOS 拷到其他机器若被 Gatekeeper 拦截，先执行 `xattr -cr FavAPI`
- 源码运行默认不开窗口；`FAVAPI_WINDOW=1 python main.py` 强制开窗

## HTTP API 摘要

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/platforms` | 平台元信息（是否已实现、支持 action） |
| GET/POST | `/api/v1/accounts` | 账号列表 / 创建 |
| GET/PATCH/DELETE | `/api/v1/accounts/{id}` | 详情 / 改名、启停 / 删除 |
| POST | `/api/v1/accounts/{id}/login` | 打开有头浏览器扫码登录（202，轮询 status） |
| GET | `/api/v1/accounts/{id}/status` | 检查登录态并同步修正账号状态 |
| POST | `/api/v1/fetch` | 统一抓取入口（同步流式 / `async_run` 异步） |
| GET | `/api/v1/tasks`、`/api/v1/tasks/{id}` | 任务记录 |
| GET | `/api/v1/favorites` | 收藏数据查询（account_id/platform/limit/offset） |
| GET/POST/… | `/api/v1/schedules` | 定时同步调度（cron） |
| GET/POST/… | `/api/v1/downloads` | 内容下载队列 |
| GET/… | `/api/v1/tags`、`/api/v1/ai/tag`、`/api/v1/ai/agents` | 标签与 AI 打标 |

### 抓取示例

```bash
# 同步等待返回（默认）
curl -X POST http://127.0.0.1:8300/api/v1/fetch -H "Content-Type: application/json" \
  -d '{"platform":"douyin","account_id":"acc_xxx","action":"list_favorites","params":{"count":50}}'

# 异步：立即返回 task_id，之后轮询任务接口
curl -X POST http://127.0.0.1:8300/api/v1/fetch -H "Content-Type: application/json" \
  -d '{"platform":"douyin","account_id":"acc_xxx","action":"list_favorites","params":{"count":50},"async_run":true}'
```

响应含 `result_count`（本次抓到条数）、`new_favorites`（新增收藏数）、`cursor` / `has_more`（增量翻页：下次把 cursor 传入 params 即从上次位置继续）。

### 微信收藏导入

微信适配器不需要扫码登录，`list_favorites` 在参数中提供 `json_path` 指向 JSON 文件：

```json
{"json_path": "C:/path/to/messages.json", "count": 0}
```

先用 [LifeArchiveProject/WeChatDataAnalysis](https://github.com/LifeArchiveProject/WeChatDataAnalysis) 导出微信收藏，再导入生成的 `conversations/.../messages.json`。`count` 限制本次导入数量，`cursor` 分批导入。

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `FAVAPI_HOST` / `FAVAPI_PORT` | 127.0.0.1 / 8300 | 监听地址 |
| `FAVAPI_DATA_DIR` | `./data` | 数据库、浏览器 profile、下载目录 |
| `FAVAPI_PLATFORMS_DIR` | `./platforms` | 声明式平台目录（platform.json 热加载） |
| `FAVAPI_HEADLESS` | `0` | 抓取/检查是否无头（抖音对无头检测严格，保持 0） |
| `FAVAPI_WINDOW` / `FAVAPI_NO_WINDOW` | — | 强制开窗 / 强制纯服务（默认：便携包开窗，源码运行不开） |

声明式平台可配置 Playwright 代理：默认 `"proxy": "auto"` 自动读取 `HTTPS_PROXY/HTTP_PROXY` 或 Windows 系统 Internet Settings；也可显式指定 `"http://127.0.0.1:7890"` 或带认证的 `{"server":"http://...","username":"...","password":"..."}`。

## 项目结构

```
main.py                  # 入口：纯服务 / pywebview 窗口模式
FavAPI.spec              # PyInstaller 打包配置
app/
├── config.py            # 配置（含便携包 sys.frozen 路径适配）
├── database.py          # aiosqlite + 表结构
├── models.py            # Pydantic 请求/响应模型
├── server.py            # FastAPI 应用工厂
├── api/                 # accounts / fetch / queries / schedules / downloads / tags / ai_tag / agents / settings
├── services/
│   ├── browser.py       # Playwright 持久化 profile + 并发控制
│   ├── account_manager.py / data_store.py / task_executor.py
│   ├── schedule_store.py / download_worker.py / download_store.py
│   └── ai_tagging.py / agent_store.py / app_settings.py
├── platforms/           # 9 个 Python 适配器 + declarative 声明式引擎 + registry
└── web/router.py        # web/dist 静态托管
platforms/               # 声明式平台定义（platform.json + 图标），运行时可热加载
web/                     # React 控制台（vite build → web/dist，详见 web/README.md）
scripts/build_portable.sh# 便携包一键构建
tests/                   # 解析器单测 + API 冒烟（不依赖浏览器）
```

## 测试

```bash
.venv/bin/python tests/test_parser.py   # 抖音解析器单测
.venv/bin/python tests/smoke_test.py    # API + 数据层冒烟（自动使用临时数据目录）
# 另有 bilibili / xiaohongshu / youtube 解析器单测、抖音 API client 单测、调度 e2e 测试
# Windows: .venv/Scripts/python.exe tests/...
```

## 新增平台指引

- **声明式（推荐，纯配置）**：`platforms/<name>/platform.json` 声明 `home_url`、`login_cookies` 及响应拦截字段映射，服务启动自动加载，`POST /api/v1/platforms/reload` 热刷新；参考 `platforms/threads/platform.json`
- **Python 适配器（需要登录/复杂解析时）**：`app/platforms/<name>/` 实现 `BasePlatformAdapter`（login / check_login_status / fetch_favorites），在 `registry.py` 注册；页面与 API 自动识别

## 已知限制

- 抖音登录态检查采用 cookie 存在性启发式（`sessionid`）；失效会在抓取时被发现并标记账号 `expired`
- 浏览器类抓取依赖页面滚动触发接口，单次条数有上限（部分平台 `MAX_COUNT`=500，0 为全部），更多数据用 `cursor` 增量翻页
- 登录/抓取会打开有头浏览器窗口，属预期行为；同一账号并发请求会串行排队
- 便携包未内置 Node.js，快手 API 直连在无 Node 环境不可用（会明确报错提示安装）
