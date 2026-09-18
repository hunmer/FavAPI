"""本地一键启动：python main.py"""
import os
import sys
import threading
import time
import atexit
import subprocess
from pathlib import Path


_single_instance_handle = None
_single_instance_lock_file = None


def _release_single_instance_lock():
    """释放单实例锁（atexit 与更新重启前调用，后者须先放锁再拉新实例）。"""
    global _single_instance_handle, _single_instance_lock_file
    if _single_instance_lock_file is not None:
        try:
            import fcntl

            fcntl.flock(_single_instance_lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            _single_instance_lock_file.close()
        except OSError:
            pass
        _single_instance_lock_file = None
    if _single_instance_handle is not None:
        try:
            import ctypes

            ctypes.WinDLL("kernel32").CloseHandle(_single_instance_handle)
        except Exception:
            pass
        _single_instance_handle = None


def _acquire_single_instance() -> bool:
    """确保生产窗口模式只运行一个 FavAPI 进程。

    pywebview/打包程序可能被外部启动器重复拉起；使用命名 Mutex 可在
    启动服务和创建窗口前直接拦截重复实例，避免出现多个原生窗口。
    """
    global _single_instance_handle, _single_instance_lock_file

    if os.name != "nt":
        # Unix: flock 是进程级锁，进程崩溃时由内核自动释放，不会留下死锁。
        import fcntl

        lock_path = Path(config.DATA_DIR) / ".favapi-single-instance.lock"
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = lock_path.open("a+")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            print("[FavAPI] 已有实例运行，退出重复启动", file=sys.stderr)
            return False
        except OSError as exc:
            if "lock_file" in locals():
                lock_file.close()
            print(f"[FavAPI] 无法创建单实例锁（{exc}），继续启动", file=sys.stderr)
            return True

        _single_instance_lock_file = lock_file
        atexit.register(_release_single_instance_lock)
        return True

    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    handle = kernel32.CreateMutexW(None, False, "Local\FavAPI.SingleInstance")
    if not handle:
        print("[FavAPI] 无法创建单实例锁，继续启动", file=sys.stderr)
        return True

    _single_instance_handle = handle
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        print("[FavAPI] 已有实例运行，退出重复启动", file=sys.stderr)
        kernel32.CloseHandle(handle)
        _single_instance_handle = None
        return False

    atexit.register(_release_single_instance_lock)
    return True

# Windows 下 stderr 默认 GBK，会导致日志中文在 procm 等采集端乱码
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx
import uvicorn

from app import config

_server: uvicorn.Server | None = None
_serve_thread: threading.Thread | None = None
_webview_window = None  # pywebview 窗口，供更新就绪时编程关闭
_restart_requested = False


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


def _on_update_ready():
    """自动更新安装就绪（updater 后台线程调用）：优雅退出，让新版生效。"""
    global _restart_requested
    _restart_requested = True
    print("更新已安装，正在退出以便新版生效……", flush=True)
    _shutdown_server()  # 先释放端口，避免与重启的新实例冲突
    if _webview_window is not None:
        _webview_window.destroy()  # 使 webview.start() 返回，主流程进入退出路径
    # 无窗口模式：should_exit 使 uvicorn.run() 返回，主流程同样进入退出路径


def _open_window():
    global _webview_window
    if _restart_requested:
        return  # 更新在开窗前已就绪：无需再开旧版窗口，直接走退出/重启路径
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

    _webview_window = webview.create_window(
        "FavAPI", url, width=1280, height=820, min_size=(960, 600)
    )
    webview.start()  # 阻塞至窗口关闭（含更新就绪时的编程关闭）
    _shutdown_server()


def _restart_if_requested():
    """进程退出前拉起新实例。Windows 由更新批处理负责（其搬运耗时已确保老进程先退出）；
    macOS 此处重启，但必须先释放单实例锁，否则新实例会被自己拦下。"""
    if not (_restart_requested and getattr(sys, "frozen", False)):
        return
    if sys.platform == "darwin":
        _release_single_instance_lock()
        subprocess.Popen([sys.executable])


if __name__ == "__main__":
    if not _acquire_single_instance():
        raise SystemExit(0)

    from app.services import updater

    updater.start_background_check(_on_update_ready)

    use_window = (
        os.environ.get("FAVAPI_NO_WINDOW") != "1"
        and (getattr(sys, "frozen", False) or os.environ.get("FAVAPI_WINDOW") == "1")
    )
    if use_window:
        _serve_in_thread()
        _open_window()
    else:
        _serve_in_thread()  # 同样走 Server 对象，使 on_update_ready 能优雅停服
        try:
            while _serve_thread.is_alive():
                _serve_thread.join(timeout=1)
        except KeyboardInterrupt:
            _shutdown_server()
    _restart_if_requested()
