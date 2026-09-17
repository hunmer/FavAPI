# 常见问题（FAQ）

**Q: API 直连抓取返回空/被识别？**
部分平台（抖音/小红书/快手/TikTok/Threads）校验 TLS/HTTP2 指纹，httpx 会被拒。项目用 curl_cffi impersonate + 各自签名方案（xhshow、Node sig_vm、GraphQL token）。原理与排查看 `docs/api-fetch-integration-guide.md`。

**Q: 抖音写操作（取消收藏/点赞）报签名错误？**
2026-09 起抖音写接口 JS 签名强校验，须走浏览器页面内 fetch hook 加签的路径（adapter 内已实现），不要改回纯 HTTP。

**Q: 登录/抓取弹出浏览器窗口正常吗？**
正常。默认有头（FAVAPI_HEADLESS=0），平台对无头检测严格；抓取中勿关窗口。同账号并发会串行排队（profile 锁）。

**Q: 抓取报「登录态缺失」/账号变 expired？**
cookie 过期（判定多为存在性启发式；小红书用 DOM 判据）。重新扫码登录即可，status 接口检测到恢复会自动改回 active。

**Q: 想抓超过单次上限？**
用响应 `cursor` 增量翻页：下次请求把 cursor 放进 params。

**Q: 抓取响应只有 100 条详情？**
items 截断 100 防超大 payload；result_count/new_favorites 是全量统计，完整数据走 `GET /api/v1/favorites`。

**Q: B 站同一视频出现在多个收藏夹？**
favorites 表以 (account, platform, content_id, fav_media_id) 唯一，同一视频多收藏夹会存多行（有意设计）。

**Q: 微信收藏怎么导入？**
微信无需登录：用 WeChatDataAnalysis 导出后，在账号详情上传 messages.json 或 `params.json_path` 指向文件；count 限批量、cursor 分批。

**Q: 新平台不想写 Python 怎么办？**
根 `platforms/<name>/platform.json` 声明式配置（拦截 URL、字段路径映射、滚动参数），`POST /api/v1/platforms/reload` 热加载。需要登录后才能抓的记得配 login_cookies。

**Q: 下载任务一直 pending？**
download_worker 每 2s 扫描、并发默认 1（settings 可调 1–3）。确认 yt-dlp/videodl 已安装；B 站等需 cookie 的平台依赖账号 cookie 快照（抓取后自动刷新，也可手动 GET /accounts/{id}/cookies）。

**Q: 定时计划到点没触发？**
调度循环 30s 粒度；上轮任务 pending/running 会跳过本轮；失败也会推进 next_run_at 防刷屏。看日志与 schedules.last_task_id。

**Q: 前端页面 404 / 白屏？**
HashRouter 下刷新无碍；若后端 `GET /` 提示"请先构建"，需 `cd web && npm run build`。dev 模式前端在 127.0.0.1:3000，`/api` 代理到 8300（FAVAPI_BACKEND 可覆盖）。

**Q: Windows 下服务起不来 / Playwright 报 NotImplementedError？**
dev 命令必须带 `--loop asyncio:ProactorEventLoop`（procm 的 dev 命令已内置），SelectorEventLoop 不支持子进程。

**Q: 终端中文乱码？**
main.py 已重配置 UTF-8；新增入口脚本要保留这段。Windows 默认 GBK。

**Q: 数据存在哪里？怎么重置？**
`data/favapi.db` + `data/profiles/`（登录态）+ `data/downloads/`。删账号自动清理 favorites 与 profile；整体重置删 data 目录后重启。

**Q: 测试会动真实数据吗？**
不会：smoke_test 用 FAVAPI_DATA_DIR 临时目录隔离；但根目录 verify_bili_*.py 会用真实 cookie 真删收藏，运行前看清脚本。
