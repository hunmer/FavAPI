# 入口与启动

## 入口文件

- `main.py` — 一键启动：stdout/stderr 重配置 UTF-8 → **单实例锁**（Windows 命名 Mutex / POSIX flock，防 pywebview/打包程序被启动器重复拉起）→ uvicorn 跑 daemon 线程（窗口模式下主线程留给 pywebview，macOS 要求主线程跑 UI）→ 可选 pywebview 窗口（`webview.create_window` 指向本地服务）。
- `app/server.py` — `app = create_app()`，dev 模式 `uvicorn app.server:app --reload` 直接引用。
- `web/src/main.tsx` — 前端入口（详见 [web/claude/entrypoints.md](../web/claude/entrypoints.md)）。
- `tests/*.py` — 各自可独立运行（`__main__` runner），也可被 pytest 收集。

## 自动更新（仅 frozen 便携包启用）

`app/services/updater.py`：启动时后台线程经 tufup（TUF）refresh 元数据 → 发现新版本 → 下载（优先增量补丁）→ 安装 → 回调让主流程优雅退出并重启。macOS purge 安装目录（保留 data/、platforms/、pw-browsers/）+ copytree(symlinks=True)；Windows 用 robocopy 批处理（进程退出后搬运文件并拉起新实例）。任何失败只记日志，不影响当前版本。源码运行（非 frozen）不启用。

## 启动流程

1. `main.py` 读 `config.HOST/PORT`（默认 127.0.0.1:8300），抢单实例锁。
2. 导入 `app.server` → `create_app()`：注册 accounts（含 platforms_router）/ agents / ai_tag / covers / downloads / fetch / follows / notifications / queries / schedules / settings / tags 共 12 模块 13 个 router → `mount_web(app)`。
3. lifespan 启动：`db.connect()`（建目录、WAL、10 表、老库迁移）→ `data_store.interrupt_stale_tasks()`（残留 running 任务标 failed）+ `download_store.requeue_stale_running()`（残留 running 下载重新入队）→ `scheduler.start()`（30s 循环）→ `download_worker.start()`（2s 循环）→ `cover_worker.start()`。
4. lifespan 关闭（逆序）：cover_worker → download_worker → scheduler → `db.close()`。
5. `mount_web`：`web/dist/index.html` 存在则挂 StaticFiles 托管 SPA；否则 `GET /` 返回"先构建前端"提示页。
6. frozen 包：`updater.start_background_check(_on_update_ready)` 后台检查；更新就绪 → 优雅退出（销毁 webview 窗口 / uvicorn should_exit）→ 重启新实例（先放单实例锁）。

## 首次部署顺序

```bash
# Windows（macOS 对应 .venv/bin/python）
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m playwright install chromium   # 首次必须
cd web && npm install && npm run build                     # 需要控制台界面时
.venv/Scripts/python.exe main.py
```

正式分发走 GitHub Actions（`.github/workflows/release.yml`）：矩阵构建 Win/mac 便携包（PyInstaller 按 `FavAPI.spec` + vite build + 内置 Chromium）。

## 运行时后台任务（均为 asyncio.create_task，无任务队列）

| 任务 | 触发 | 生命周期 |
|------|------|----------|
| 扫码登录 | `POST /accounts/{id}/login` | 最长 300s（LOGIN_TIMEOUT），完成清内存标记 |
| 异步抓取 | `/fetch` + `async_run=true` | 全流程入库，异常只记日志 |
| 同步抓取 | `/fetch` 默认 | `asyncio.wait_for` 300s（FETCH_TIMEOUT） |
| SSE 抓取/打标/操作/同步 | `/fetch/stream` 等 | 客户端断开即任务标 failed |
| 调度循环 | lifespan | 每 30s 扫到期 schedule 并触发 |
| 下载循环 | lifespan | 每 2s 取 pending，子进程 yt-dlp/videodl/aria2c |
| 封面本地化 | lifespan / 缩略图请求顺手入队 | cover_worker 后台消费 |
| AI 打标 | action=ai_tag | 批次 20 条/批，LLM 超时 120s |
| 更新检查 | main.py（仅 frozen） | 后台线程，就绪后回调优雅退出 |

## procm 持久化进程

`procm-commands.json` 定义 Windows 5 条 + macOS 4 条 + 前端 web 共 10 个命令。注意 Windows `dev` 命令的 `--loop asyncio:ProactorEventLoop` 与 `--reload-dir app` 参数有特殊原因（见文件内 desc），改动前先读说明。
