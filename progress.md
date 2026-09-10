# Progress Log

## Session 1 — 2026-09-10

- 读取 PRD.md，确认需求范围（M1–M4）
- 环境勘察：默认 python 为外部 venv；选用 py -3.13 创建项目专属 .venv
- 创建计划文件 task_plan.md / findings.md / progress.md
- Phase 1：.venv 创建成功，fastapi/uvicorn/aiosqlite/playwright/jinja2/httpx 已安装
- `playwright install chromium` 被用户取消 → **挂起，后续再装**；用户指示：优先写代码
- 进入 Phase 2–7 代码编写（一次性完成后再统一验证）

### 代码与验证（同日完成）

- 全部后端代码完成：config/database/models、平台适配器（base/registry/douyin/bilibili）、服务层（browser/account_manager/data_store/task_executor）、API（accounts/fetch/queries）、Web 界面（4 页面）、main.py 入口
- 测试：`tests/test_parser.py` 4/4 通过；`tests/smoke_test.py` 29/29 通过（临时数据目录，不依赖浏览器）
- 真实启动冒烟：uvicorn 起在 127.0.0.1:8300，页面/docs/API/创建删除账号全部正常
- README.md 完成；task_plan 全部 Phase 标记 complete
- **遗留**：~~`playwright install chromium` 待执行~~ → 已通过 procm 完成（走系统代理 127.0.0.1:7890，Chromium + Headless Shell 均下载成功，退出码 0）

### procm 配置与运行（2026-09-10）

- procm-commands.json 创建（server / dev / test-parser / test-smoke / install-browser），import-process-batch 注册到 group=favapi，room `favapi` 元数据已建
- test-parser 经 procm 启动验证：4/4 通过，退出码 0，分组与 room 关联正常
- install-browser 经 procm 启动（envs HTTP(S)_PROXY=127.0.0.1:7890）：成功
- server 经 `procm-command start` 启动（ID PEu2LL97）：http://127.0.0.1:8300 响应正常
- 剩余待用户配合：页面创建账号 → 扫码登录 → 真实抓取验证

### 真机问题修复（2026-09-10 晚，用户实测反馈）

用户实测：登录成功、抓取可出数据，但有两个问题——

1. **登录后浏览器窗口反复弹开关闭十几次** → 根因：前端每 4s 轮询 /status，check_login_status 以有头模式开浏览器且在 profile 锁上排队，登录结束后排队请求挨个执行造成窗口闪烁。
   修复：check_login_status 固定无头（只读 cookie 不导航）；/status 在浏览器占用（browser.is_busy）时快速返回 busy 不开浏览器；前端轮询遇 busy 继续等待。
2. **收藏抓取不自动滚动翻页** → 根因：抖音个人页滚动在内部容器而非 window，且 Playwright 鼠标初始在 (0,0) 悬停导航栏，wheel 滚不动内容区。
   修复：JS 扫描真实可滚动容器设 scrollTop + 鼠标移至内容中心再补 wheel；新增连续 6 轮无新增数据的止损（MAX_STALL_ROUNDS）；全流程调试日志（批次捕获/滚动轮次/去重计数）。

附加：main.py 强制 stdout/stderr UTF-8，修复 procm 日志中文乱码；server.py logging.basicConfig 输出 favapi.* 日志。

**验证**（用用户已登录账号 acc_c5fce32f 真机抓取两次）：
- count=30 → success 30 条：首批 10 条 + 滚动触发 3 批，收满即停，has_more=True
- count=35 → success 35 条：初始 5 批 + 1 轮容器滚动（scrollTop=1247/2107）再 3 批，去重 80 条
- 服务已重启（PEu2LL97），回归测试 parser 4/4、smoke 29/29 通过
