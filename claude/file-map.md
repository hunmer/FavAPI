# 文件地图

```
FavAPI/
├── main.py                    # 一键启动入口（uvicorn）
├── requirements.txt           # fastapi/uvicorn/aiosqlite/playwright/jinja2/httpx
├── procm-commands.json        # procm 持久化进程命令定义
├── AGENTS.md                  # 工作区 Agent 行为规范
├── PRD.md                     # 产品需求（表结构/API/里程碑的事实来源）
├── README.md                  # 面向使用者的说明
├── task_plan.md / progress.md / findings.md   # 2026-09-10 构建期规划产物（历史记录，勿当产品文档）
├── data/                      # 运行时生成（git 忽略）：favapi.db + profiles/
├── tests/
│   ├── test_parser.py         # 抖音 parser 单测（4 用例）
│   └── smoke_test.py          # API + 数据层冒烟（29 检查项）
└── app/
    ├── config.py              # 路径/服务/浏览器常量（环境变量可覆盖）
    ├── database.py            # SCHEMA + Database 单例 db
    ├── models.py              # Pydantic 请求/响应模型
    ├── server.py              # create_app + lifespan + app 实例
    ├── utils.py               # now_iso / new_id
    ├── api/
    │   ├── accounts.py        # 账号 CRUD + login(202) + status + /platforms
    │   ├── fetch.py           # POST /api/v1/fetch
    │   └── queries.py         # /tasks /favorites
    ├── services/
    │   ├── browser.py         # Playwright 会话：profile Lock + 全局 Semaphore
    │   ├── account_manager.py # 账号 CRUD + 登录防重入
    │   ├── data_store.py      # contents/favorites/tasks 持久化
    │   └── task_executor.py   # 抓取任务生命周期 + 校验
    ├── platforms/
    │   ├── base.py            # BasePlatformAdapter / FetchResult / LoginExpiredError
    │   ├── registry.py        # 注册表（底部 import 即注册）
    │   ├── douyin/
    │   │   ├── adapter.py     # 登录/检查/拦截抓取（核心，最复杂）
    │   │   ├── parser.py      # 接口 JSON → 通用 content 行
    │   │   └── constants.py   # URL/cookie/滚动参数
    │   └── bilibili/
    │       ├── adapter.py     # 占位（NotImplementedError）
    │       └── constants.py
    └── web/
        ├── router.py          # 4 个页面路由
        └── templates/         # base + index/account_detail/tasks/favorites.html（原生 JS 调 JSON API）
```

所有 `__init__.py` 均为空文件。`.codegraph/` 为本地索引（git 忽略）。

修改热点提示：抖音抓取行为调参看 `douyin/constants.py`；并发/超时看 `config.py`；接口行为看 `api/` + `task_executor.py`。
