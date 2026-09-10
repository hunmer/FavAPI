# 入口与启动

## 入口文件

- `main.py` — 本地一键启动：重配置 stdout/stderr 为 UTF-8 后 `uvicorn.run("app.server:app", host, port)`。
- `app/server.py` — ASGI 应用实例 `app = create_app()`（dev 模式 `uvicorn app.server:app --reload` 直接引用）。
- `tests/test_parser.py`、`tests/smoke_test.py` — 可独立运行的测试入口（`if __name__ == "__main__"`）。

## 启动流程

1. `main.py` 读 `app.config.HOST/PORT`（环境变量 `FAVAPI_HOST`/`FAVAPI_PORT`，默认 127.0.0.1:8300）。
2. uvicorn 加载 `app.server:app` → 模块导入时 `create_app()` 已执行：注册 accounts / platforms / fetch / queries / web 五个 router。
3. lifespan 启动：`db.connect()` → 创建 `DATA_DIR` → aiosqlite 连接 + WAL → executescript 建四表三索引。
4. lifespan 关闭：`db.close()`。

## 首次部署顺序

```bash
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m playwright install chromium   # 首次必须，需几分钟
.venv/Scripts/python.exe main.py
```

## 运行时后台任务

- 登录：`POST /accounts/{id}/login` → `asyncio.create_task(_do_login)`，最长等扫码 300s（`config.LOGIN_TIMEOUT`），完成/异常后清理内存防重入标记。
- 异步抓取：`POST /api/v1/fetch` 带 `async_run=true` → `asyncio.create_task(_guarded_run)`，异常只记日志不打崩循环。
- 同步抓取：`asyncio.wait_for(..., FETCH_TIMEOUT=300s)` 超时则任务标 failed。

## procm 持久化进程

`procm-commands.json` 定义 server / dev / test-parser / test-smoke / install-browser 五个命令（group=favapi，room `favapi`）。改完代码后用 procm 重启服务，不要手动留 orphan 进程。
