# 入口与启动

## 入口文件

- `main.py` — 一键启动：stdout/stderr 重配置 UTF-8 后 `uvicorn.run("app.server:app", host, port)`。
- `app/server.py` — `app = create_app()`，dev 模式 `uvicorn app.server:app --reload` 直接引用。
- `web/src/main.tsx` — 前端入口（详见 [web/claude/entrypoints.md](../web/claude/entrypoints.md)）。
- `tests/*.py` — 各自可独立运行（`__main__` runner），也可被 pytest 收集。

## 启动流程

1. `main.py` 读 `config.HOST/PORT`（默认 127.0.0.1:8300）。
2. 导入 `app.server` → `create_app()`：注册 accounts（含 platforms_router）/ agents / ai_tag / downloads / fetch / queries / schedules / settings / tags 共 10 个 router → `mount_web(app)`。
3. lifespan 启动：`db.connect()`（建目录、WAL、8 表 5 索引、老库迁移）→ `scheduler.start()`（30s 循环）→ `download_worker.start()`（2s 循环）。
4. lifespan 关闭（逆序）：`download_worker.stop()` → `scheduler.stop()` → `db.close()`。
5. `mount_web`：`web/dist/index.html` 存在则挂 StaticFiles 托管 SPA；否则 `GET /` 返回"先构建前端"提示页。

## 首次部署顺序

```bash
# Windows（macOS 对应 .venv/bin/python）
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m playwright install chromium   # 首次必须
cd web && npm install && npm run build                     # 需要控制台界面时
.venv/Scripts/python.exe main.py
```

## 运行时后台任务（均为 asyncio.create_task，无任务队列）

| 任务 | 触发 | 生命周期 |
|------|------|----------|
| 扫码登录 | `POST /accounts/{id}/login` | 最长 300s（LOGIN_TIMEOUT），完成清内存标记 |
| 异步抓取 | `/fetch` + `async_run=true` | 全流程入库，异常只记日志 |
| 同步抓取 | `/fetch` 默认 | `asyncio.wait_for` 300s（FETCH_TIMEOUT） |
| SSE 抓取/打标/操作 | `/fetch/stream` 等 | 客户端断开即任务标 failed |
| 调度循环 | lifespan | 每 30s 扫到期 schedule 并触发 |
| 下载循环 | lifespan | 每 2s 取 pending，子进程 yt-dlp/videodl |
| AI 打标 | action=ai_tag | 批次 20 条/批，LLM 超时 120s |

## procm 持久化进程

`procm-commands.json` 定义 Windows 5 条 + macOS 4 条 + 前端 web 共 10 个命令。注意 Windows `dev` 命令的 `--loop asyncio:ProactorEventLoop` 与 `--reload-dir app` 参数有特殊原因（见文件内 desc），改动前先读说明。
