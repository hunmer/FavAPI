# 开发约定与规则

## 命令（见 procm-commands.json，已注册到 procm group=favapi）

| 用途 | 命令 |
|------|------|
| 启动服务 | `procm-command start server`（或 `.venv/Scripts/python.exe main.py`，127.0.0.1:8300） |
| 开发热重载 | `procm-command start dev` |
| 解析器单测 | `.venv/Scripts/python.exe tests/test_parser.py` |
| API 冒烟测试 | `.venv/Scripts/python.exe tests/smoke_test.py`（自动用临时数据目录，不依赖浏览器） |
| 安装浏览器内核 | `.venv/Scripts/python.exe -m playwright install chromium`（首次必须） |

## 环境约定

- Python 解释器必须用项目内 `.venv/Scripts/python.exe`（py -3.13 创建）。**系统默认 `python` 是外部 agent 的 venv，禁止用它安装依赖。**
- 平台 Windows / Git Bash；路径在脚本中注意反斜杠转义，引用路径始终加双引号。
- `main.py` 已把 stdout/stderr 重配置为 UTF-8，避免中文日志在采集端乱码——改动入口时保留这段。

## 代码风格

- 全异步（async/await），数据库只用 `app.database.db` 单例连接。
- 服务层互相只 import 需要的模块；平台适配器只依赖 `services.browser`，不得反向依赖 api 层。
- 新增平台：在 `app/platforms/<name>/` 实现 `BasePlatformAdapter` 三个抽象方法，在 `registry.py` 底部 `register(...)`；页面下拉框与 action 校验自动生效。
- 时间统一 `utils.now_iso()`（本地时区、秒精度）；ID 统一 `utils.new_id(prefix)`。
- JSON 入库列（extra / statistics / raw_data / request_params）读出时用 try/except json.loads 兜底为空值。

## 禁止 / 注意事项

- 不要提交或读取 `data/` 目录内容（含真实登录态 profile 与数据库）。
- 抖音相关功能保持有头模式；不要为了"干净"把 HEADLESS 默认改成 1。
- 同一账号的浏览器操作天然串行（profile Lock），不要绕过 `browser.session()` 直接开 Playwright。
- 测试不得污染真实数据：smoke_test 通过 `FAVAPI_DATA_DIR` 环境变量隔离，新测试沿用该模式。
- API 校验错误统一 `FetchValidationError` → 400；HTTPException detail 用中文短句。
