# 对外接口

## REST API（前缀 /api/v1，完整定义见 http://127.0.0.1:8300/docs）

### 平台

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/platforms` | 平台元信息列表：platform / display_name / implemented / supported_actions |

### 账号

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/accounts` | 列表（含 `logging_in` 内存态标记） |
| POST | `/api/v1/accounts` | 创建（body: platform, name?, extra?），201；未知/未实现平台 400 |
| GET | `/api/v1/accounts/{id}` | 详情，404 不存在 |
| PATCH | `/api/v1/accounts/{id}` | 改名 / 启停（status: active/disabled/expired） |
| DELETE | `/api/v1/accounts/{id}` | 删除（级联删 favorites + profile 目录；contents 保留） |
| POST | `/api/v1/accounts/{id}/login` | 202，后台开有头浏览器等扫码；重复发起 409；返回 poll_url |
| GET | `/api/v1/accounts/{id}/status` | cookie 检查登录态并回写修正账号 status；浏览器忙时快速返回 `busy: true, logged_in: null` |

### 抓取

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/fetch` | body: `{platform, account_id, action, params?, async_run?}`。默认同步 200 返回结果；`async_run=true` 返回 202 + task_id。校验失败 400（账号不存在/平台不一致/未实现/action 不支持/已禁用） |

同步响应字段：`task_id, account_id, platform, action, status(success/failed), result_count, new_favorites, cursor, has_more, items[≤100 条摘要], error_message?`。

抖音 params：`count`（默认 20，上限 500）、`cursor`（上次返回值，从该偏移继续取）。

### 任务与数据

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/tasks?limit=&account_id=` | 任务列表，按开始时间倒序（limit 1–500，默认 50） |
| GET | `/api/v1/tasks/{task_id}` | 任务详情，404 不存在 |
| GET | `/api/v1/favorites?account_id=&platform=&limit=&offset=` | 收藏查询：favorites JOIN contents，含拼好的 `url`，返回 `{total, items, limit, offset}` |

## Web 页面（Jinja2，不进 OpenAPI schema）

| 路径 | 页面 |
|------|------|
| `/` | 账号列表（创建账号、发起登录、轮询状态） |
| `/accounts/{account_id}` | 账号详情（登录、填 count 触发抓取） |
| `/tasks` | 任务历史 |
| `/favorites` | 收藏数据浏览 |

页面数据全部由前端 JS 调上述 JSON API 获取，服务端只渲染模板骨架。

## 内部扩展接口（代码级）

- `BasePlatformAdapter`：新增平台的抽象契约（login / check_login_status / fetch_favorites）。
- `registry.register(adapter)`：注册新平台，`/platforms`、账号创建下拉框、action 校验自动生效。
