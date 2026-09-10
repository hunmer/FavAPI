# FavAPI — 多平台个人收藏抓取 HTTP API 服务

本地/私有化部署的「个人收藏数据同步中台」：通过真实浏览器登录态抓取各平台个人收藏，支持多账号管理，结果持久化到 SQLite。

当前状态：**抖音完整实现 + Bilibili 占位**（详见 [PRD.md](./PRD.md)）。

## 功能

- **多账号 Session 管理**：每个账号独立浏览器 profile（登录态持久化），有头扫码登录、状态检查、禁用/删除
- **HTTP API 抓取**：`POST /api/v1/fetch` 指定平台 + 账号 + 操作，支持同步等待或异步轮询
- **SQLite 持久化**：accounts / fetch_tasks / contents / favorites 四表，重复抓取自动去重
- **Web 管理界面**：账号列表、登录、触发抓取、任务记录、数据浏览，完整闭环
- **平台适配器架构**：新增平台只需实现 `BasePlatformAdapter` 并注册

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 2. 安装浏览器内核（首次必须，约需几分钟）
.venv/Scripts/python.exe -m playwright install chromium

# 3. 启动服务（默认 http://127.0.0.1:8300）
.venv/Scripts/python.exe main.py
```

打开 [http://127.0.0.1:8300](http://127.0.0.1:8300) 进入管理界面，或 [http://127.0.0.1:8300/docs](http://127.0.0.1:8300/docs) 查看 API 文档。

### 使用流程（闭环）

1. 页面「账号」→ 选择平台（抖音）→ 填名称 → 创建账号
2. 点击「登录」→ 弹出浏览器窗口 → 抖音 App 扫码 → 页面自动轮询显示登录结果
3. 进入账号详情 → 填 count → 「开始抓取」（会打开浏览器自动滚动加载，请勿关闭）
4. 页面「数据」查看抓取到的收藏；「任务」查看执行历史

## HTTP API 摘要

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/platforms` | 平台元信息（是否已实现、支持 action） |
| GET/POST | `/api/v1/accounts` | 账号列表 / 创建 |
| GET/PATCH/DELETE | `/api/v1/accounts/{id}` | 详情 / 改名、启停 / 删除 |
| POST | `/api/v1/accounts/{id}/login` | 打开有头浏览器扫码登录（202，轮询 status） |
| GET | `/api/v1/accounts/{id}/status` | 检查登录态并同步修正账号状态 |
| POST | `/api/v1/fetch` | 统一抓取入口（见下） |
| GET | `/api/v1/tasks`、`/api/v1/tasks/{id}` | 任务记录 |
| GET | `/api/v1/favorites` | 收藏数据查询（account_id/platform/limit/offset） |

### 抓取示例

```bash
# 同步等待返回（默认）
curl -X POST http://127.0.0.1:8300/api/v1/fetch -H "Content-Type: application/json" \
  -d '{"platform":"douyin","account_id":"acc_xxx","action":"list_favorites","params":{"count":50}}'

# 异步：立即返回 task_id，之后轮询任务接口
curl -X POST http://127.0.0.1:8300/api/v1/fetch -H "Content-Type: application/json" \
  -d '{"platform":"douyin","account_id":"acc_xxx","action":"list_favorites","params":{"count":50},"async_run":true}'
```

响应含 `result_count`（本次抓到条数）、`new_favorites`（新增收藏数）、`cursor` / `has_more`（增量翻页用：下次请求把 cursor 传入 params 即从上次位置继续）。

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `FAVAPI_HOST` / `FAVAPI_PORT` | 127.0.0.1 / 8300 | 监听地址 |
| `FAVAPI_DATA_DIR` | `./data` | 数据库与浏览器 profile 根目录 |
| `FAVAPI_HEADLESS` | `0` | 抓取/检查是否无头（抖音对无头检测严格，保持 0） |

## 项目结构

```
app/
├── config.py            # 配置
├── database.py          # aiosqlite + PRD 表结构
├── models.py            # Pydantic 请求/响应模型
├── server.py            # FastAPI 应用工厂
├── api/                 # accounts / fetch / queries 路由
├── services/
│   ├── browser.py       # Playwright 持久化 profile + 并发控制
│   ├── account_manager.py
│   ├── data_store.py    # contents upsert / favorites / 任务记录
│   └── task_executor.py # 任务生命周期 + 结果入库
├── platforms/
│   ├── base.py          # BasePlatformAdapter 抽象
│   ├── registry.py      # 注册表
│   ├── douyin/          # 登录 / 状态检查 / listcollection 拦截抓取 / 解析
│   └── bilibili/        # 占位（NotImplementedError + 友好提示）
└── web/                 # Jinja2 管理界面
tests/                   # parser 单测 + API 冒烟（不依赖浏览器）
```

## 测试

```bash
.venv/Scripts/python.exe tests/test_parser.py   # 抖音解析器单测
.venv/Scripts/python.exe tests/smoke_test.py    # API + 数据层冒烟（自动使用临时数据目录）
```

## 新增平台指引

1. `app/platforms/<name>/`：实现 `BasePlatformAdapter`（login / check_login_status / fetch_favorites），解析结果输出为通用 content 行（见 `douyin/parser.py`）
2. 在 `registry.py` 注册实例
3. 页面与 API 自动识别（创建账号下拉框、action 校验均来自注册表）

## 已知限制

- 抖音登录态检查采用 cookie 存在性启发式（`sessionid`）；失效会在抓取时被发现并标记账号 `expired`
- 抓取依赖页面滚动触发接口，单次上限 500 条（`MAX_COUNT`），更多数据用 `cursor` 增量翻页
- 登录/抓取会打开有头浏览器窗口，属预期行为；同一账号并发请求会串行排队
