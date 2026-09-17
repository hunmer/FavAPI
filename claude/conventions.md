# 开发约定与规则

## 命令（procm-commands.json，group=favapi；Windows 与 macOS 两套）

| 用途 | Windows | macOS |
|------|---------|-------|
| 启动服务 | `procm-command start server` | `procm-command start server-mac` |
| 开发热重载 | `procm-command start dev`（须带 `--loop asyncio:ProactorEventLoop`，见文件内说明） | `procm-command start dev-mac` |
| 解析器单测 | `test-parser` | `test-parser-mac` |
| API 冒烟 | `test-smoke` | `test-smoke-mac` |
| 安装浏览器内核 | `install-browser` | `install-browser-mac` |
| 前端 dev | `procm-command start web`（127.0.0.1:3000，`/api` 代理 8300） | 同左 |

- Python 解释器：Windows 用 `.venv/Scripts/python.exe`，macOS 用 `.venv/bin/python`。**系统默认 `python` 可能是外部 venv，禁止用它装依赖。**
- 前端生产部署：`cd web && npm run build` → 产物 `web/dist` 由 FastAPI 直接托管；后端检测不到 dist 时首页会提示先构建。
- 改完代码用 procm 重启服务，不留 orphan 进程。

## 环境与平台差异

- 双平台开发（Windows + macOS）；路径引用始终加双引号，脚本注意反斜杠转义。
- Windows 下 `main.py` 已把 stdout/stderr 重配置为 UTF-8（防 GBK 乱码），改入口时保留。
- Windows dev 模式必须显式 `--loop asyncio:ProactorEventLoop`，否则子进程（Playwright/下载）报 NotImplementedError。

## 代码风格（后端）

- 全异步；数据库只用 `app.database.db` 单例连接。
- 服务层互相只 import 需要的模块；平台适配器不得反向依赖 api 层。
- 时间统一 `utils.now_iso()`；ID 统一 `utils.new_id(prefix)`（如 `acc_` / `task_` / `dl_`）。
- JSON 入库列（extra/statistics/raw_data/request_params/tags）读出时 try/except json.loads 兜底。
- API 校验错误统一 `FetchValidationError` → 400；HTTPException detail 用中文短句。
- 抓取/写操作涉及风控：批量写操作之间加请求间隔（参考 FolderPicker 批量删除、B 站取消收藏的间隔防风控逻辑）。

## 新增平台

优先看两条路径：
1. **声明式**（无签名或简单拦截）：在根 `platforms/<name>/platform.json` 写 capture/fields 映射，重启或调 `POST /api/v1/platforms/reload`。
2. **Python 适配器**：`app/platforms/<name>/` 实现 `BasePlatformAdapter`（login / check_login_status / fetch_favorites，可选 fetch_favorites_api / execute_api_operation），在 `registry.py` 底部注册；页面下拉框、action 校验、操作表单自动生效。

详细接入流程见 `docs/api-fetch-integration-guide.md`（TLS 指纹原理、四步接入、踩坑记录）。

## 禁止 / 注意事项

- 不要提交或读写 `data/`（真实登录态 profile、数据库、下载文件、头像）。
- 抖音等平台功能保持有头模式（`FAVAPI_HEADLESS=0`），不要把默认改无头。
- 浏览器操作必须经 `browser.session()`（profile 锁 + 信号量），不得绕过直接开 Playwright。
- 测试必须用 `FAVAPI_DATA_DIR` 隔离数据。
- 根目录 `verify_bili_*.py` 含硬编码真实 cookie，属临时人工验证脚本，勿当测试维护、勿提交新 cookie。
- 依赖未锁版本；升级 fastapi/starlette 注意 API 签名变化。
