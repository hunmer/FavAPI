# 模块职责

单一 Python 包 `app/`，四个子包 + 五个顶层模块。

## 顶层模块

| 模块 | 职责 |
|------|------|
| `app/config.py` | 全局常量：DATA_DIR / DB_PATH / PROFILES_DIR、HOST/PORT、HEADLESS、超时、并发上限。全部可被环境变量覆盖 |
| `app/database.py` | `Database` 类（aiosqlite 单连接 + WAL + SCHEMA 初始化）与全局单例 `db`；提供 execute / query_one / query_all |
| `app/models.py` | Pydantic 请求/响应模型（AccountCreate/Update/Out、FetchRequest、TaskOut、FavoriteItem 等） |
| `app/server.py` | FastAPI 应用工厂 `create_app()` + lifespan（连接/关闭数据库）+ 挂载全部 router；模块级 `app` 实例即 ASGI 入口 |
| `app/utils.py` | `now_iso()`、`new_id(prefix)` |

## app/api（HTTP 路由层）

| 文件 | 职责 |
|------|------|
| `accounts.py` | `/api/v1/accounts` CRUD、PATCH 启停/改名；`/api/v1/platforms` 元信息；`POST /{id}/login`（202 + 后台扫码）、`GET /{id}/status`（cookie 检查并回写状态；busy 时快速返回） |
| `fetch.py` | `POST /api/v1/fetch` 统一抓取入口，同步返回或 202+task_id |
| `queries.py` | `/api/v1/tasks`、`/api/v1/favorites` 查询（分页） |

## app/services（服务层）

| 文件 | 职责 |
|------|------|
| `account_manager.py` | 账号 CRUD（profile 路径生成、删除时清理 favorites + profile 目录）；登录防重入内存集合 |
| `task_executor.py` | `start_fetch`：请求校验（账号/平台一致/action 合法/未禁用）→ 任务创建 → 同步执行或后台执行；`LoginExpiredError` → 标记账号 expired；错误消息友好化（浏览器内核未安装等） |
| `data_store.py` | `save_fetch_result`（upsert contents → insert favorites，计算 new_favorites）、`list_favorites`（JOIN 查询 + content URL 模板）、任务表读写 |
| `browser.py` | `session()` 上下文管理器：持久化 profile 打开 Chromium，per-profile Lock + 全局 Semaphore；`has_login_cookies` / `is_busy` 辅助 |

## app/platforms（平台适配器）

| 文件 | 职责 |
|------|------|
| `base.py` | `BasePlatformAdapter` 抽象（login / check_login_status / fetch_favorites）、`AccountContext`、`FetchResult`、`LoginExpiredError` |
| `registry.py` | 注册表：register / get_adapter / platform_infos；模块底部导入即注册抖音与 Bilibili |
| `douyin/adapter.py` | 扫码登录（轮询 cookie）、登录态检查（无头只读 cookie）、收藏抓取（goto 收藏页 → 拦截 listcollection 响应 → 容器滚动 + 滚轮事件 → 去重合并 → cursor 切片） |
| `douyin/parser.py` | `parse_listcollection` / `parse_aweme`：接口 JSON → 通用 content 行（title 取 desc 首行、cover 多候选、collected_at 多字段名尝试） |
| `douyin/constants.py` | URL、拦截接口路径、登录 cookie 键、count/滚动参数 |
| `bilibili/` | 占位：`implemented=False`，所有方法抛 NotImplementedError，API 层转 400 友好提示 |

## app/web（管理界面）

| 文件 | 职责 |
|------|------|
| `router.py` | 4 个页面路由（`/`、`/accounts/{id}`、`/tasks`、`/favorites`），Jinja2 渲染，`include_in_schema=False` |
| `templates/` | base.html（布局+导航）+ 4 页面；原生 JS 调 `/api/v1` JSON 接口，无构建链 |

## tests

| 文件 | 职责 |
|------|------|
| `test_parser.py` | parser 纯函数单测（4 用例），可直接运行或 pytest 收集 |
| `smoke_test.py` | httpx ASGITransport 全链路冒烟（29 检查项）：平台/账号 CRUD/抓取校验/任务/收藏入库回读/删除级联/Web 页面/OpenAPI |
