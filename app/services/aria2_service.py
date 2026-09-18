"""aria2c 下载服务：管理本地 aria2c RPC 进程，通过 aria2p 提交/跟踪/移除任务。

aria2c 二进制由系统提供（PATH 中查找）；aria2p 为纯 Python RPC 客户端（pip install aria2p）。
RPC 固定监听 127.0.0.1:6800：先探测已有服务（用户自启的 aria2 也直接复用），
没有才由本服务拉起子进程，随应用退出终止。
"""
import asyncio
import logging
import shutil

from app.services.download_worker import downloads_root
from app.utils import now_iso

logger = logging.getLogger("favapi.aria2")

RPC_HOST = "127.0.0.1"
RPC_PORT = 6800
POLL_INTERVAL = 1.0          # 任务状态轮询间隔（秒）
_INSTALL_HINT = (
    "未找到 aria2c 可执行文件，请先安装："
    "Windows: winget install aria2.aria2（或 scoop install aria2）；"
    "macOS: brew install aria2；Linux: 包管理器安装 aria2"
)

_proc: asyncio.subprocess.Process | None = None
_client = None  # aria2p.API，懒加载单例


def installed() -> bool:
    return shutil.which("aria2c") is not None


def _aria2p_api():
    """构建 aria2p 客户端（不发起连接；import 失败说明 pip 包未装）。"""
    global _client
    if _client is None:
        try:
            import aria2p
        except ImportError as exc:
            raise RuntimeError("未安装 aria2p（Python RPC 客户端）：pip install aria2p") from exc
        _client = aria2p.API(aria2p.Client(host=f"http://{RPC_HOST}", port=RPC_PORT, secret=""))
    return _client


def _rpc_alive() -> bool:
    try:
        _aria2p_api().client.get_version()
        return True
    except Exception:
        return False


async def ensure_rpc():
    """确保 RPC 可用：已有服务直接复用，否则拉起 aria2c 子进程。"""
    global _proc
    if _rpc_alive():
        return _aria2p_api()
    if not installed():
        raise RuntimeError(_INSTALL_HINT)
    if _proc is not None and _proc.returncode is None:
        _proc.kill()  # 进程还在但 RPC 不通：重启
    log_dir = downloads_root() / ".logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = (log_dir / "aria2c.log").open("a", encoding="utf-8")
    log.write(f"\n===== [{now_iso()}] 启动 aria2c RPC（端口 {RPC_PORT}）=====\n")
    log.flush()
    _proc = await asyncio.create_subprocess_exec(
        "aria2c",
        "--enable-rpc", f"--rpc-listen-port={RPC_PORT}",
        f"--dir={downloads_root()}",
        "--continue=true", "--allow-overwrite=true", "--auto-file-renaming=false",
        "--console-log-level=warn",
        stdout=log, stderr=asyncio.subprocess.STDOUT,
    )
    logger.info("aria2c RPC 子进程已启动（pid=%s，端口 %s）", _proc.pid, RPC_PORT)
    for _ in range(20):  # 最多等 5s RPC 就绪（端口被其他程序占用时会失败）
        await asyncio.sleep(0.25)
        if _rpc_alive():
            return _aria2p_api()
    raise RuntimeError(
        f"aria2c RPC 启动失败（端口 {RPC_PORT} 可能被占用），详见 {log_dir / 'aria2c.log'}"
    )


async def shutdown():
    """应用退出时终止自管的 aria2c 子进程（复用外部服务时无操作）。"""
    global _proc
    if _proc is not None and _proc.returncode is None:
        _proc.terminate()
        try:
            await asyncio.wait_for(_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            _proc.kill()
    _proc = None


def _to_aria2_options(headers: dict) -> dict:
    """平台直链附带的下载头（User-Agent / Referer 等）→ aria2 选项。"""
    options: dict[str, str] = {}
    lines = []
    for key, value in (headers or {}).items():
        name = str(key).strip()
        if not name:
            continue
        if name.lower() in ("user-agent", "referer"):
            options[name.lower()] = str(value)
        else:
            lines.append(f"{name}: {value}")
    if lines:
        options["header"] = lines
    return options


async def add(url: str, out_dir, filename: str, headers: dict | None = None) -> str:
    """提交一个下载（返回 gid）。目录/文件名由调用方决定，headers 携带平台下载头。"""
    api = await ensure_rpc()
    options = {"dir": str(out_dir), "out": filename, **_to_aria2_options(headers or {})}
    download = await asyncio.to_thread(api.add_uris, [url], options=options)
    logger.info("aria2 任务已提交：gid=%s out=%s", download.gid, out_dir / filename)
    return download.gid


def _fmt_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}GB"


async def wait(download_id: str, gid: str, on_update=None) -> tuple[bool, str]:
    """轮询任务直到终态，返回 (是否成功, 失败信息)。

    on_update(text) 节流回调进度（百分比/已下载/速度）；任务被本服务移除
    （暂停/取消）时返回 (False, "已移除")，终态由调用方结合库内状态判断。
    """
    from app.services import download_store

    api = _aria2p_api()
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            d = await asyncio.to_thread(api.get_download, gid)
        except Exception:
            continue  # RPC 瞬断：下一轮重试
        total = d.total_length
        done = d.completed_length
        speed = d.download_speed
        pct = f"{done * 100 / total:.1f}%" if total else "0%"
        if on_update:
            await on_update(
                f"{pct} {_fmt_size(done)}/{_fmt_size(total)}"
                + (f" {_fmt_size(speed)}/s" if speed > 0 else "")
            )
        if d.status == "complete":
            return True, ""
        if d.status == "removed":
            return False, "任务已移除"
        if d.status == "error":
            return False, d.error_message or "aria2 下载出错"
        # 暂停/取消：库内已写终态则直接退出，不再覆盖
        cur = await download_store.get_download(download_id)
        if cur and cur["status"] in ("canceled", "paused"):
            return False, cur["status"]


def remove(gid: str) -> bool:
    """移除任务（暂停/取消时调用）；失败（任务已结束/不存在）返回 False。"""
    api = _aria2p_api()
    try:
        d = api.get_download(gid)
        api.remove([d])
        return True
    except Exception:
        return False
