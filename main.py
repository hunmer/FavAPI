"""本地一键启动：python main.py"""
import os
import sys
import threading
import time

# Windows 下 stderr 默认 GBK，会导致日志中文在 procm 等采集端乱码
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx
import uvicorn

from app import config


_server: uvicorn.Server | None = None
_serve_thread: threading.Thread | None = None


def _serve_in_thread():
    """后端跑 daemon 线程：窗口模式下主线程留给 pywebview（macOS 要求主线程跑 UI）。"""
    global _server, _serve_thread
    _server = uvicorn.Server(
        uvicorn.Config("app.server:app", host=config.HOST, port=config.PORT)
    )
    _serve_thread = threading.Thread(target=_server.run, daemon=True)
    _serve_thread.start()


def _shutdown_server():
    """通知 uvicorn 优雅退出（lifespan shutdown 停调度器/下载工作器并落盘）。"""
    if _server is not None:
        _server.should_exit = True
    if _serve_thread is not None:
        _serve_thread.join(timeout=8)  # 超时则放弃等待，daemon 兜底 + WAL 恢复


def _open_window():
    import webview

    url = f"http://{config.HOST}:{config.PORT}"
    # 后端就绪前开窗会白屏，轮询 /docs 直至可用（最长 30s）
    for _ in range(60):
        try:
            if httpx.get(f"{url}/docs", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)

    webview.create_window("FavAPI", url, width=1280, height=820, min_size=(960, 600))
    webview.start()  # 阻塞至窗口关闭，daemon 服务线程随之结束


if __name__ == "__main__":
    use_window = (
        os.environ.get("FAVAPI_NO_WINDOW") != "1"
        and (getattr(sys, "frozen", False) or os.environ.get("FAVAPI_WINDOW") == "1")
    )
    if use_window:
        _serve_in_thread()
        _open_window()
        _shutdown_server()
    else:
        uvicorn.run("app.server:app", host=config.HOST, port=config.PORT)
