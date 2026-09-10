# 常见问题（FAQ）

**Q: 启动报「Executable doesn't exist」/ 浏览器内核未安装？**
首次使用必须执行 `.venv/Scripts/python.exe -m playwright install chromium`（下载慢可走代理）。task_executor.friendly_error 会把该错误转成中文提示。

**Q: 登录/抓取时弹出可见浏览器窗口，正常吗？**
正常且必要：抖音对无头检测严格，抓取默认有头（`FAVAPI_HEADLESS=0`）。只有「登录态检查」固定无头（不导航页面，只读 cookie）。抓取过程中请勿关闭窗口。

**Q: 同一账号同时发两个请求会怎样？**
排队。每个 profile 一把 asyncio Lock（同账号串行）+ 全局最多 2 个浏览器并发。登录等待期间轮询 status 不会堆积——busy 时直接快速返回不排队。

**Q: 登录成功过，为什么抓取报「登录态缺失」？**
登录判定是 cookie 存在性启发式（sessionid / sessionid_ss），cookie 过期即失效。此时账号会被标记 `expired`，重新扫码登录即可（status 接口检测到恢复会自动改回 active）。

**Q: 想抓超过 500 条怎么办？**
单次上限 `MAX_COUNT=500`（douyin/constants.py）。用响应里的 `cursor` 做增量翻页：下次请求 `params.cursor = 上次返回的 cursor`。

**Q: 抓取只返回前 100 条详情？**
响应内嵌 items 截断到 100（防超大 payload），`result_count`/`new_favorites` 是全量统计；完整数据用 `GET /api/v1/favorites` 分页查。

**Q: 选 Bilibili 报「暂未实现」？**
预期行为（PRD M4 占位）。adapter 全部抛 NotImplementedError，API 层转 400 友好提示，不影响抖音。

**Q: 终端中文日志乱码？**
main.py 已把 stdout/stderr 重配置为 UTF-8；若新增入口脚本未做此处理，Windows 默认 GBK 会乱码。Git Bash 下 curl -d 传中文会编码损坏，用 httpx 或页面测试。

**Q: 数据存在哪里？怎么重置？**
`data/favapi.db`（SQLite，WAL 模式）+ `data/profiles/`（浏览器登录态）。重置账号用 DELETE 接口（自动清理 favorites 与 profile）；整体重置直接删 data 目录（服务需重启）。

**Q: 为什么 POST /login 返回 202 而不是等结果？**
扫码需要用户交互，HTTP 请求不能阻塞。前端按返回的 poll_url 轮询 `GET /accounts/{id}/status` 观察结果。

**Q: 测试会动我的真实数据吗？**
不会。smoke_test 启动前把 `FAVAPI_DATA_DIR` 指到临时目录，且不依赖浏览器内核。
