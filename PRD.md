# PRD：多平台个人收藏抓取 HTTP API 服务（Douyin 优先 + Bilibili 占位）

## 1. 产品概述

### 1.1 背景
需要一个可扩展的本地/私有化服务，通过 HTTP API 获取用户在各平台「个人收藏」中的内容，并支持多账号管理。

### 1.2 核心目标
- 通过真实浏览器登录态抓取个人收藏数据
- 支持多账号（Session）管理
- HTTP 请求可指定账号执行
- 抓取结果持久化到本地 SQLite
- 架构支持多平台扩展（当前实现抖音，预留 Bilibili）

### 1.3 产品定位
本地/私有化部署的「个人收藏数据同步中台」，而非公开爬虫服务。

---

## 2. 功能需求

### 2.1 多账号 Session 管理（核心）

| 功能 | 说明 |
|------|------|
| 创建 Session | 为每个平台账号创建一个独立 Session（绑定浏览器 profile） |
| 登录 | 支持有头模式扫码/账号密码登录，登录态持久化 |
| 状态检查 | 检测登录是否有效（cookie / session 有效性） |
| 删除 / 禁用 | 删除或临时禁用某个 Session |
| 列表查看 | 展示所有 Session 及其状态、最后使用时间、关联平台 |

**Session 数据结构（建议）**

```json
{
  "account_id": "acc_001",
  "platform": "douyin",
  "name": "我的抖音主号",
  "status": "active",          // active / expired / disabled
  "profile_path": "./profiles/douyin_acc_001",
  "last_login_at": "2026-09-10T12:00:00",
  "last_used_at": "2026-09-10T13:00:00",
  "extra": {}
}
```

### 2.2 HTTP API 执行抓取（支持指定账户）

**统一入口示例**

```
POST /api/v1/fetch
Content-Type: application/json

{
  "platform": "douyin",
  "account_id": "acc_001",
  "action": "list_favorites",
  "params": {
    "count": 50,
    "cursor": null
  }
}
```

**参数说明**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| platform | string | 是 | 平台标识：`douyin` / `bilibili` |
| account_id | string | 是 | 指定使用的 Session |
| action | string | 是 | 操作类型（见各平台定义） |
| params | object | 否 | 平台特定参数（count、cursor 等） |

**抖音支持的 action**
- `list_favorites`：获取默认收藏列表
- `list_collects`：获取收藏夹（专辑）列表（后续）
- `get_collect_videos`：获取指定收藏夹内容（后续）

### 2.3 数据持久化（SQLite）

所有抓取结果必须写入本地 SQLite，便于历史查询、去重、增量同步。

**核心表设计**

```sql
-- 账号 / Session 表
CREATE TABLE accounts (
    account_id      TEXT PRIMARY KEY,
    platform        TEXT NOT NULL,
    name            TEXT,
    status          TEXT DEFAULT 'active',
    profile_path    TEXT,
    last_login_at   TEXT,
    last_used_at    TEXT,
    created_at      TEXT,
    extra           TEXT          -- JSON
);

-- 抓取任务记录
CREATE TABLE fetch_tasks (
    task_id         TEXT PRIMARY KEY,
    account_id      TEXT,
    platform        TEXT,
    action          TEXT,
    request_params  TEXT,         -- JSON
    status          TEXT,         -- pending / running / success / failed
    result_count    INTEGER,
    error_message   TEXT,
    started_at      TEXT,
    finished_at     TEXT
);

-- 视频 / 内容主表（通用）
CREATE TABLE contents (
    content_id      TEXT PRIMARY KEY,   -- 平台内容唯一ID（如 aweme_id / bvid）
    platform        TEXT NOT NULL,
    account_id      TEXT,               -- 归属哪个账号抓取的
    title           TEXT,
    description     TEXT,
    author_id       TEXT,
    author_name     TEXT,
    cover_url       TEXT,
    duration        INTEGER,
    statistics      TEXT,               -- JSON: digg/comment/share...
    raw_data        TEXT,               -- 原始完整 JSON
    first_seen_at   TEXT,
    last_seen_at    TEXT,
    UNIQUE(platform, content_id)
);

-- 收藏关系表（账号收藏了哪些内容）
CREATE TABLE favorites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT,
    platform        TEXT,
    content_id      TEXT,
    collected_at    TEXT,               -- 平台侧收藏时间（如有）
    fetched_at      TEXT,
    UNIQUE(account_id, platform, content_id)
);
```

**写入策略**
- 抓取成功后：先 upsert `contents`，再写入 `favorites` 关系
- 支持按 `account_id + platform` 查询历史收藏
- 任务执行过程写入 `fetch_tasks`，便于排查

### 2.4 简易后端 Web 管理界面

提供基础管理页面（推荐 FastAPI + 简单前端，或 Jinja2 模板 + HTMX / 纯 HTML）：

| 页面 / 功能 | 说明 |
|-------------|------|
| Session 列表 | 展示所有账号、平台、状态、最后使用时间 |
| 新增 Session | 选择平台 → 填写名称 → 启动有头浏览器登录 |
| Session 详情 | 查看登录状态、触发手动刷新登录、删除 |
| 任务记录 | 查看历史抓取任务及结果数量 / 错误信息 |
| 数据浏览 | 简单列表查看某账号下已抓取的收藏内容 |
| 手动触发抓取 | 在页面上选择账号 + 填写 count 后发起抓取 |

**最低可用要求**
- 能完成「创建账号 → 登录 → 发起抓取 → 查看结果」闭环
- 不要求复杂权限系统（初期单用户本地使用）

### 2.5 多平台支持架构

采用 **平台适配器（Platform Adapter）** 模式，便于扩展。

```
platforms/
├── base.py                 # 抽象基类
├── douyin/
│   ├── adapter.py          # 实现登录、抓取逻辑
│   ├── parser.py
│   └── constants.py
└── bilibili/
    ├── adapter.py          # 占位实现
    └── constants.py
```

**抽象接口示例**

```python
class BasePlatformAdapter(ABC):
    @abstractmethod
    async def login(self, account: Account) -> bool: ...
    
    @abstractmethod
    async def check_login_status(self, account: Account) -> bool: ...
    
    @abstractmethod
    async def fetch_favorites(self, account: Account, params: dict) -> FetchResult: ...
```

#### 2.5.1 抖音（Douyin）—— 完整实现

- 目标页面：`https://www.douyin.com/user/self?showTab=favorite_collection`
- 拦截接口：`POST /aweme/v1/web/aweme/listcollection/`
- 滚动加载 + 解析 `aweme_list`
- 支持 `count`、`cursor`

#### 2.5.2 Bilibili —— 占位（后续扩展）

**预留能力（本版本只做接口与页面占位）**

| 能力 | 状态 | 说明 |
|------|------|------|
| Session 创建 / 登录 | 占位 | 页面可选平台「Bilibili」，点击后提示「即将支持」 |
| 收藏列表抓取 | 未实现 | 预留 action：`list_favorites` |
| 数据表结构 | 已支持 | `platform = 'bilibili'` 可直接写入 |
| Adapter | 空实现 | 抛出 `NotImplementedError` 或返回友好提示 |

后续实现时重点关注：
- 登录方式（扫码 / Cookie）
- 收藏夹 API（如 `/x/v3/fav/resource/list` 等）
- 是否需要浏览器，或可直接用 Cookie 请求

---

## 3. 接口定义（完善版）

### 3.1 账号管理

```
GET    /api/v1/accounts                     # 列表
POST   /api/v1/accounts                     # 创建
GET    /api/v1/accounts/{account_id}        # 详情
DELETE /api/v1/accounts/{account_id}        # 删除
POST   /api/v1/accounts/{account_id}/login  # 启动登录流程
GET    /api/v1/accounts/{account_id}/status # 检查登录状态
```

### 3.2 抓取执行

```
POST /api/v1/fetch
{
  "platform": "douyin",
  "account_id": "acc_001",
  "action": "list_favorites",
  "params": {
    "count": 50,
    "cursor": null
  }
}
```

### 3.3 任务与数据查询

```
GET /api/v1/tasks                           # 任务列表
GET /api/v1/tasks/{task_id}                 # 任务详情
GET /api/v1/favorites?account_id=xxx&platform=douyin&limit=50
```

---

## 4. 技术架构建议

```
┌─────────────────────────────────────────────┐
│              Web 管理界面 (简单)               │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────┐
│              FastAPI  HTTP API               │
│  - 账号管理  - 抓取入口  - 任务查询  - 数据查询   │
└────────────────────┬────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼────────┐    ┌─────────▼─────────┐
│  Session Manager│    │   Task Executor   │
│  (多账号 profile)│    │  (异步任务队列)     │
└────────┬────────┘    └─────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │  Platform Adapters    │
         │  Douyin / Bilibili…   │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │  Playwright / Browser │
         │  (本地 or Browserless)│
         └───────────────────────┘
                     │
         ┌───────────▼───────────┐
         │      SQLite DB        │
         └───────────────────────┘
```

**推荐技术选型**
- 后端：FastAPI + SQLAlchemy / aiosqlite
- 浏览器：Playwright（本地持久化 profile）
- 前端：初期可用 Jinja2 + HTMX 或简单 Vue/React
- 任务：可先同步执行，后续用 asyncio 队列或 Celery

---

## 5. 非功能需求

| 项目 | 要求 |
|------|------|
| 数据安全 | 仅处理用户自己的登录态数据，不存储密码明文 |
| 并发 | 初期单账号串行，多账号可有限并发（受浏览器实例限制） |
| 存储 | SQLite 单文件，便于备份与迁移 |
| 可扩展 | 新增平台只需实现 Adapter，不影响现有接口 |
| 部署 | 支持本地一键启动（Docker 可选） |

---

## 6. 里程碑规划

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| M1 | 单账号抖音收藏抓取 + SQLite 存储 + 基础 HTTP API | P0 |
| M2 | 多账号 Session 管理 + 指定 account_id 执行 | P0 |
| M3 | 简易 Web 管理界面（账号列表 / 登录 / 触发抓取 / 查看数据） | P1 |
| M4 | Bilibili 占位（平台选择 + Adapter 骨架 + 友好提示） | P1 |
| M5 | 收藏夹（专辑）支持、增量同步、任务队列优化 | P2 |

---

## 7. 验收标准（更新）

1. 可创建多个抖音 Session，并分别完成登录
2. HTTP 请求传入不同 `account_id` 时，使用对应账号执行抓取
3. 抓取结果正确写入 SQLite，且可通过 API / 页面查询
4. Web 管理界面可完成「新增账号 → 登录 → 抓取 → 查看结果」完整流程
5. 选择 Bilibili 平台时，系统给出明确「暂未实现」提示，不影响抖音功能
6. 单次请求指定 `count`，返回数量符合预期（或全部可用数据）

---