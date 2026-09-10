# 依赖与配置

## 运行依赖（requirements.txt，无版本锁定）

| 包 | 用途 |
|----|------|
| fastapi | Web 框架 + Pydantic 模型 |
| uvicorn[standard] | ASGI 服务器 |
| aiosqlite | 异步 SQLite（单连接 + WAL） |
| playwright | Chromium 持久化 profile 浏览器自动化（首次需 `playwright install chromium`） |
| jinja2 | Web 管理界面模板 |
| httpx | 仅测试使用（ASGITransport 冒烟），未列入 requirements 也可运行服务；当前已随 fastapi 生态存在，requirements 未含它 |

> 注意：requirements.txt 未固定版本；Python 为 3.13（项目 `.venv`）。无 lock 文件、无 pyproject.toml。

## 环境变量（app/config.py）

| 变量 | 默认 | 说明 |
|------|------|------|
| `FAVAPI_HOST` / `FAVAPI_PORT` | 127.0.0.1 / 8300 | HTTP 监听 |
| `FAVAPI_DATA_DIR` | `<仓库根>/data` | 数据库 + 浏览器 profile 根目录；测试用它隔离 |
| `FAVAPI_HEADLESS` | `0` | 抓取是否无头；抖音检测严格，保持 0 |

派生路径：`DB_PATH = DATA_DIR/favapi.db`，`PROFILES_DIR = DATA_DIR/profiles`。

## 代码内常量（config.py）

| 常量 | 值 | 说明 |
|------|-----|------|
| `LOGIN_TIMEOUT` | 300s | 扫码登录最长等待 |
| `FETCH_TIMEOUT` | 300s | 单次同步抓取整体超时 |
| `MAX_CONCURRENT_BROWSERS` | 2 | 全局并发浏览器上限（Semaphore） |
| `PAGE_TIMEOUT` | 30000ms | Playwright 默认页面超时 |

## 平台常量

- 抖音（douyin/constants.py）：`FAVORITES_URL`（个人页收藏 tab）、拦截接口 `/aweme/v1/web/aweme/listcollection`、登录 cookie `sessionid`/`sessionid_ss`、`DEFAULT_COUNT=20`、`MAX_COUNT=500`、`SCROLL_INTERVAL_MS=1800`、`MAX_SCROLL_ROUNDS=300`、`MAX_STALL_ROUNDS=6`。
- Bilibili（bilibili/constants.py）：仅 PLATFORM / DISPLAY_NAME / NOT_IMPLEMENTED_MSG。

## 配置文件

| 文件 | 用途 |
|------|------|
| `procm-commands.json` | procm 持久化进程命令（server/dev/test-parser/test-smoke/install-browser） |
| `.gitignore` | 忽略 .venv / data 等 |
| `AGENTS.md` | 本工作区 Agent 行为规范（输出格式、工具偏好） |
