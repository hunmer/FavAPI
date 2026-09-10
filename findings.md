# Findings

## 环境

- 默认 `python`（PATH 首位）= hermes-agent venv 3.11.9，**不可用于本项目安装依赖**
- 系统可用：`py -3.13`（C:\Users\Administrator\AppData\Local\Programs\Python\Python313）→ 用于创建项目 `.venv`
- 平台 win32，Git Bash shell；路径含反斜杠，脚本内注意转义/使用原始字符串

## PRD 关键要点（提炼）

- 平台适配器模式：`BasePlatformAdapter`（login / check_login_status / fetch_favorites）
- 抖音目标页 `https://www.douyin.com/user/self?showTab=favorite_collection`；拦截 `POST /aweme/v1/web/aweme/listcollection/`，解析 `aweme_list`，支持 count / cursor
- 登录：有头扫码，登录态持久化在浏览器 profile（`./profiles/<platform>_<account_id>`）
- SQLite 四表：accounts / fetch_tasks / contents / favorites（结构 PRD 已给定，extra/raw_data/statistics 存 JSON 字符串）
- 写入顺序：upsert contents → 写 favorites 关系；任务过程写 fetch_tasks
- API：/api/v1/accounts CRUD+login+status；/api/v1/fetch；/api/v1/tasks；/api/v1/favorites
- Bilibili：仅占位（页面可选、创建后动作返回友好「暂未实现」，adapter 抛 NotImplementedError）

## 技术研究结论

- Starlette（当前版本）`Jinja2Templates.TemplateResponse` 新签名：`(request, name, context)`；老写法 `(name, {"request": ...})` 会把 context 当模板名
- httpx `await client.get(x).json()` 优先级坑：await 作用于整个表达式 → 需 `(await client.get(x)).json()`
- aiosqlite 单连接 + WAL 对本地单用户足够；测试中异常路径可能因连接线程不退出而挂起，正常关闭无问题
- 测试用 `app.router.lifespan_context(app)` 手动驱动 lifespan + `httpx.ASGITransport`，保证测试与服务同事件循环（aiosqlite 连接安全）
- 抖音登录判定：cookie `sessionid` / `sessionid_ss` 存在即视为已登录；失效在抓取时发现并标记 expired
- listcollection 响应结构：`{aweme_list, cursor, has_more, total}`；aweme 内收藏时间字段多个候选（collect_time / collected_at / collect_date），parser 逐个尝试
- Git Bash 下 curl -d 传中文会编码损坏，服务端正常（httpx 验证通过）

## 真机调试结论（2026-09-10）

- 抖音个人页（/user/self）滚动发生在**内部 div 容器**而非 window：`window.scrollBy` / 默认位置 `mouse.wheel` 都无效；需 JS 扫描 `scrollHeight > clientHeight+200 && clientHeight>300` 的容器设 scrollTop，并把鼠标移到内容中心再 wheel
- listcollection 每批 10 条，响应含 cursor（时间戳形态）与 has_more；页面初次加载可能连出多批（恢复滚动位置时）
- 状态轮询设计教训：凡会开浏览器的接口被高频轮询时，必须（a）无头化纯 cookie 检查（b）占用时快速返回，否则请求在 profile 锁排队、结束后集中弹窗
- Windows 服务进程日志中文乱码：main.py 入口处 `sys.stdout/stderr.reconfigure(encoding='utf-8')` 解决（procm 采集 UTF-8）
- 用户账号首批数据验证：count=30/35 两次真机抓取均成功，滚动止损与日志符合预期

## 测试结果（2026-09-10）

- `tests/test_parser.py`：4/4 通过
- `tests/smoke_test.py`：29/29 通过（平台元信息/账号 CRUD/抓取校验/Bilibili 友好提示/任务生命周期/收藏入库去重回读/删除清理/页面渲染/OpenAPI）
- 真实 uvicorn 启动冒烟：`/`、`/docs`、accounts/platforms API、创建+删除账号均正常（端口 8300）
- **待办**：`playwright install chromium` 被挂起；真实扫码登录与抓取需浏览器内核 + 用户交互，未验证
