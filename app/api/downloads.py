"""下载队列 API：列表 / 入队 / 重试 / 删除（取消）/ 日志查看 / 工具链检测。"""
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models import DownloadCreate, DownloadOut
from app.services import download_store, download_worker

router = APIRouter(prefix="/api/v1/downloads", tags=["downloads"])

# downloader -> PyPI 包名（videodl 的发布包名为 videofetch；aria2c 二进制为系统安装，
# pip 层面只管理其 RPC 客户端 aria2p）
TOOLCHAIN = {"yt-dlp": "yt-dlp", "videodl": "videofetch", "aria2c": "aria2p"}


async def _get_or_404(download_id: str) -> dict:
    row = await download_store.get_download(download_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"下载任务不存在：{download_id}")
    return row


async def _run_cmd(args: list[str], timeout: float = 60) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    return proc.returncode, out.decode("utf-8", errors="replace").strip()


async def _detect_tool(downloader: str) -> dict:
    """检测下载器是否安装并取版本：先跑可执行文件 --version，失败用 pip show 兜底。"""
    base = download_worker._resolve_command(downloader)
    if base:
        try:
            rc, out = await _run_cmd([*base, "--version"], timeout=15)
        except (OSError, asyncio.TimeoutError):
            rc, out = 1, ""
        if rc == 0 and out:
            return {"installed": True, "version": out.splitlines()[0].strip()}
    if downloader == "aria2c":
        # aria2c 为系统安装的二进制，pip 层无对应包（aria2p 仅是 RPC 客户端），不做 pip 兜底
        return {"installed": False, "version": None}
    rc, out = await _run_cmd([sys.executable, "-m", "pip", "show", TOOLCHAIN[downloader]])
    if rc == 0:
        m = re.search(r"^Version:\s*(\S+)", out, re.M)
        if m:
            return {"installed": True, "version": m.group(1)}
    return {"installed": False, "version": None}


@router.get("/toolchain")
async def get_toolchain():
    return {name: await _detect_tool(name) for name in TOOLCHAIN}


@router.post("/toolchain/{downloader}/update")
async def update_toolchain(downloader: str):
    """SSE 流式执行 pip install --upgrade：line 事件逐行推送输出，done/error 结束。

    pip 进度条用 \\r 重绘同一行，行内取最后一段避免刷屏。
    """
    if downloader not in TOOLCHAIN:
        raise HTTPException(status_code=400, detail=f"不支持的下载器：{downloader}")

    def sse_msg(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def sse():
        before = await _detect_tool(downloader)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "--upgrade", TOOLCHAIN[downloader],
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                # 进度条 \r 重绘：只保留重绘后的最新内容
                line = raw.decode("utf-8", errors="replace").rstrip().split("\r")[-1].strip()
                if line:
                    yield sse_msg({"type": "line", "text": line})
            returncode = await proc.wait()
            if returncode != 0:
                yield sse_msg({"type": "error", "detail": f"pip 异常退出（退出码 {returncode}），详见上方输出"})
                return
            after = await _detect_tool(downloader)
            yield sse_msg({
                "type": "done",
                "before": before["version"],
                "after": after["version"],
                "updated": before["version"] != after["version"],
            })
        except asyncio.CancelledError:
            proc.kill()  # 客户端断开（关闭对话框）时终止 pip，避免孤儿进程
            raise

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("")
async def list_downloads():
    return {"downloads": [DownloadOut(**d).model_dump() for d in await download_store.list_downloads()]}


@router.post("", status_code=201)
async def create_download(body: DownloadCreate):
    try:
        row = await download_store.create_download(
            body.platform, body.content_id, body.title, body.url, body.downloader, body.account_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return DownloadOut(**row).model_dump()


@router.post("/{download_id}/retry", status_code=202)
async def retry_download(download_id: str):
    row = await _get_or_404(download_id)
    if row["status"] in ("pending", "running"):
        raise HTTPException(status_code=400, detail="任务仍在队列中，无需重试")
    await download_store.reset_download(download_id)
    return {"download_id": download_id, "status": "pending"}


@router.post("/{download_id}/pause", status_code=202)
async def pause_download(download_id: str):
    await _get_or_404(download_id)
    row = await download_store.pause_download(download_id)
    if row and row["status"] != "paused":
        raise HTTPException(status_code=400, detail=f"当前状态（{row['status']}）不支持暂停")
    return {"download_id": download_id, "status": "paused"}


@router.post("/{download_id}/reveal", status_code=200)
async def reveal_download(download_id: str):
    """在系统文件管理器中打开输出位置（Windows 资源管理器 / Finder / xdg-open）。

    output_path 为下载输出目录；目录被移动/删除时返回 404。
    """
    row = await _get_or_404(download_id)
    raw = str(row.get("output_path") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="该任务还没有输出位置（未开始或未完成）")
    target = Path(raw)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"输出位置不存在（可能已被移动或删除）：{raw}")
    folder = target if target.is_dir() else target.parent
    if sys.platform == "win32":
        # 文件用 /select 定位选中，目录直接打开
        args = ["explorer", "/select,", str(target)] if target.is_file() else ["explorer", str(folder)]
    elif sys.platform == "darwin":
        args = ["open", "-R", str(target)] if target.is_file() else ["open", str(folder)]
    else:
        args = ["xdg-open", str(folder)]
    subprocess.Popen(args)
    return {"revealed": True, "path": str(folder)}


@router.get("/{download_id}/log")
async def get_download_log(download_id: str):
    """该任务落盘的下载日志（.logs/{download_id}.log），未开始时 log 为空串。"""
    await _get_or_404(download_id)
    return {"download_id": download_id, "log": download_worker.read_log(download_id)}


@router.delete("/logs")
async def clear_download_logs():
    """清空全部下载日志（运行中任务的日志保留）。"""
    return {"deleted": download_worker.clear_logs()}


@router.delete("/{download_id}")
async def delete_download(download_id: str):
    row = await _get_or_404(download_id)
    if row["status"] == "running":
        await download_worker.cancel(download_id)
    await download_store.delete_download(download_id)
    download_worker.delete_log(download_id)
    return {"deleted": download_id}
