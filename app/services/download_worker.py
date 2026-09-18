"""下载工作器：后台循环执行下载队列（yt-dlp / videodl 子进程，aria2c 平台直链），支持并发与暂停。"""
import asyncio
import logging
import re
import shutil
import sys
from pathlib import Path

from app import config
from app.services import download_store
from app.services.app_settings import load_settings
from app.utils import now_iso

logger = logging.getLogger("favapi.downloader")

CHECK_INTERVAL = 2            # 队列扫描间隔（秒）
PROGRESS_WRITE_INTERVAL = 0.5  # 进度落库最小间隔（秒）

# videodl 专用解析客户端映射（装好 videodl 后自动生效；未映射平台走其通用解析器）
VIDEODL_CLIENTS = {
    "bilibili": "BilibiliVideoClient",
    "douyin": "SnapAnyVideoClient",
    "xiaohongshu": "SnapAnyVideoClient",
}

# 平台 → Cookies 域名（注入 yt-dlp 时只保留对应平台的登录态）
_PLATFORM_COOKIE_DOMAINS = {
    "bilibili": ("bilibili.com",),
    "douyin": ("douyin.com",),
    "xiaohongshu": ("xiaohongshu.com",),
    "youtube": ("youtube.com", "google.com"),
}

_task: asyncio.Task | None = None
_running: dict[str, asyncio.subprocess.Process] = {}   # download_id -> 正在执行的子进程
_aria2_gids: dict[str, list[str]] = {}                 # download_id -> aria2 任务 gid 列表（图文多张）


def downloads_root() -> Path:
    """下载根目录：设置里可改（SettingsView「下载位置」），默认 data/downloads。"""
    custom = str(load_settings().get("download_dir") or "").strip()
    return Path(custom) if custom else config.DATA_DIR / "downloads"


def _concurrency() -> int:
    try:
        return max(1, min(3, int(load_settings().get("download_concurrency") or 1)))
    except (TypeError, ValueError):
        return 1


async def start():
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run_forever())
        logger.info("下载工作器已启动（每 %ss 扫描一次队列）", CHECK_INTERVAL)


async def stop():
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    for proc in _running.values():
        proc.kill()
    _running.clear()
    logger.info("下载工作器已停止")


async def _run_forever():
    inflight: set[asyncio.Task] = set()
    while True:
        try:
            inflight = {t for t in inflight if not t.done()}
            while len(inflight) < _concurrency():
                row = await download_store.next_pending()
                if row is None:
                    break
                await download_store.update_download(
                    row["download_id"], status="running", started_at=now_iso(), progress="启动下载器..."
                )
                inflight.add(asyncio.create_task(_run_one(row)))
        except asyncio.CancelledError:
            for t in inflight:
                t.cancel()
            raise
        except Exception:
            logger.exception("下载循环异常")
        await asyncio.sleep(CHECK_INTERVAL)


def _resolve_command(downloader: str) -> list[str] | None:
    exe = shutil.which(downloader)
    if exe:
        return [exe]
    if downloader == "yt-dlp":
        # pip 安装了包但 PATH 里没有 exe 入口时兜底
        return [sys.executable, "-m", "yt_dlp"]
    return None


async def _write_cookies_file(download_id: str, account_id: str | None, platform: str) -> Path | None:
    """把账号 cookie 快照写成 Netscape 格式供 yt-dlp 使用（无快照/无匹配域名返回 None）。"""
    if not account_id:
        return None
    from app.services import account_manager

    account = await account_manager.get_account(account_id)
    if account is None:
        return None
    cookies = ((account.get("extra") or {}).get("cookies") or {}).get("cookies") or []
    domains = _PLATFORM_COOKIE_DOMAINS.get(platform)
    if domains:
        cookies = [c for c in cookies if any(d in (c.get("domain") or "") for d in domains)]
    if not cookies:
        return None

    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c.get("domain") or ""
        # domain 以 . 开头表示对该站点所有子域生效
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        expires = max(int(c.get("expires") or 0), 0)  # 会话 cookie(-1) 落为 0
        secure = bool(c.get("secure")) or domain.endswith(("youtube.com", "google.com"))
        lines.append("\t".join([
            domain, flag, c.get("path") or "/", "TRUE" if secure else "FALSE", str(expires),
            c.get("name") or "", c.get("value") or "",
        ]))
    tmp = downloads_root() / ".cookies" / f"{download_id}.cookies.txt"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n".join(lines) + "\n", "utf-8")
    return tmp


def _log_file(download_id: str) -> Path:
    """每个下载任务一份日志：downloads/.logs/{download_id}.log（重试追加，保留历史）。"""
    return downloads_root() / ".logs" / f"{download_id}.log"


def _append_log(download_id: str, text: str):
    path = _log_file(download_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{text}\n")


def read_log(download_id: str) -> str:
    try:
        return _log_file(download_id).read_text("utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def delete_log(download_id: str) -> None:
    _log_file(download_id).unlink(missing_ok=True)


def clear_logs() -> int:
    """清空全部下载日志，返回删除数（跳过正在运行的任务，其日志句柄仍被占用）。"""
    log_dir = downloads_root() / ".logs"
    if not log_dir.exists():
        return 0
    count = 0
    for path in log_dir.glob("*.log"):
        if path.stem in _running:
            continue
        path.unlink(missing_ok=True)
        count += 1
    return count


async def _run_one(row: dict):
    download_id, url = row["download_id"], row["url"]
    try:
        await _execute(row)
    except Exception as exc:
        logger.exception("下载任务 %s 执行异常", download_id)
        _append_log(download_id, f"[{now_iso()}] 内部错误：{exc}")
        await download_store.update_download(
            download_id, status="failed",
            error_message="内部错误，详见下载日志", finished_at=now_iso(),
        )


async def _execute(row: dict):
    if row["downloader"] == "aria2c":
        return await _execute_aria2(row)
    download_id, url, platform = row["download_id"], row["url"], row.get("platform") or ""
    out_dir = downloads_root() / _category_dir(
        platform, str(row.get("content_id") or ""), row.get("title") or "")
    out_dir.mkdir(parents=True, exist_ok=True)

    base = _resolve_command(row["downloader"])
    if base is None:
        # videodl 的 PyPI 发布包名为 videofetch（github.com/CharlesPikachu/videodl）
        pkg = {"yt-dlp": "yt-dlp", "videodl": "videofetch"}[row["downloader"]]
        _append_log(download_id, f"[{now_iso()}] 未找到 {row['downloader']} 可执行文件，请先安装：pip install {pkg}")
        await download_store.update_download(
            download_id, status="failed", finished_at=now_iso(),
            error_message=f"未找到 {row['downloader']} 可执行文件，请先安装：pip install {pkg}",
        )
        return

    cookies_file = None
    if row["downloader"] == "yt-dlp":
        cmd = [*base, "--newline", "--no-playlist",
               "-o", str(out_dir / "%(title).80s.%(ext)s"), url]
        cookies_file = await _write_cookies_file(download_id, row.get("account_id"), platform)
        if cookies_file is not None:
            cmd += ["--cookies", str(cookies_file)]
            logger.info("任务 %s 已注入账号 %s 的 Cookies（%s）",
                        download_id, row.get("account_id"), cookies_file.name)
        cwd = None
    else:
        cmd = [*base, "-i", url]
        client = VIDEODL_CLIENTS.get(platform)
        if client:
            cmd += ["-a", client]
        cwd = out_dir

    logger.info("下载开始 %s：%s", download_id, " ".join(cmd))
    log_path = _log_file(download_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a", encoding="utf-8")
    log.write(f"\n===== [{now_iso()}] 开始下载（{row['downloader']}） {url} =====\n命令：{' '.join(cmd)}\n")
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    _running[download_id] = proc
    tail: list[str] = []
    try:
        loop = asyncio.get_running_loop()
        last_write = 0.0
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            tail.append(line)
            tail = tail[-10:]
            log.write(f"{line}\n")
            log.flush()
            if loop.time() - last_write >= PROGRESS_WRITE_INTERVAL:
                await download_store.update_download(download_id, progress=line[-200:])
                last_write = loop.time()
        returncode = await proc.wait()

        # 暂停/取消：对应操作已写入终态，这里不覆盖
        cur = await download_store.get_download(download_id)
        if cur and cur["status"] in ("canceled", "paused"):
            action = "取消" if cur["status"] == "canceled" else "暂停"
            log.write(f"[{now_iso()}] 任务被{action}，进程已终止\n")
            return
        if returncode == 0:
            await download_store.update_download(
                download_id, status="success", progress="下载完成",
                output_path=str(out_dir), finished_at=now_iso(),
            )
            log.write(f"[{now_iso()}] 下载完成，输出目录：{out_dir}\n")
            logger.info("下载完成 %s（%s）", download_id, url)
        else:
            await download_store.update_download(
                download_id, status="failed", output_path=str(out_dir),
                error_message="\n".join(tail)[-500:] or f"退出码 {returncode}",
                finished_at=now_iso(),
            )
            tail_text = "\n".join(tail)
            log.write(f"[{now_iso()}] 下载失败（退出码 {returncode}），最近输出：\n{tail_text}\n")
            logger.warning("下载失败 %s（退出码 %s）：%s", download_id, returncode, tail_text)
    finally:
        log.close()
        _running.pop(download_id, None)
        if cookies_file is not None:
            cookies_file.unlink(missing_ok=True)


def _safe_name(title: str, content_id: str) -> str:
    """标题 → 合法文件/目录名（截断 + 去除 Windows 非法字符），空标题回落 content_id。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", str(title or "").strip())[:80].strip(" .")
    return name or content_id


def _safe_filename(title: str, content_id: str, ext: str) -> str:
    return f"{_safe_name(title, content_id)}.{ext or 'mp4'}"


def _category_dir(platform: str, content_id: str, title: str, link: dict | None = None) -> Path:
    """下载分类目录：按设置 download_category 模板渲染（相对 downloads 根的子路径）。

    变量：{platform} {id} {title} {ext} {authorName} {authorId}；
    author 信息由平台解析直链时附带（link 项），未知/空变量置空并剔除空段，
    禁止 . / .. 越界；模板为空回落 {platform}。
    """
    values = {
        "platform": platform or "misc",
        "id": content_id,
        "title": _safe_name(title, content_id),
        "ext": (link or {}).get("ext") or "",
        "authorName": _safe_name(str((link or {}).get("author_name") or ""), ""),
        "authorId": _safe_name(str((link or {}).get("author_id") or ""), ""),
    }
    template = str(load_settings().get("download_category") or "").strip() or "{platform}"

    def _sub(match: re.Match) -> str:
        return values.get(match.group(1)) or ""

    rendered = re.sub(r"\{(\w+)\}", _sub, template)
    parts = [_safe_name(p, "") for p in re.split(r"[\\/]+", rendered)]
    parts = [p for p in parts if p and p not in (".", "..")]
    return Path(*parts) if parts else Path(values["platform"])


def _pick_link_by_quality(links: list[dict], quality: str | None) -> dict:
    """按清晰度选直链：auto / 无匹配回落首个（平台推荐）。

    指定高度时：优先精确匹配；无精确档取不超标的最高一档（同高度取首个 = 推荐 CDN）。
    """
    if not links:
        raise ValueError("直链列表为空")
    if not quality or quality == "auto":
        return links[0]
    try:
        target = int(quality)
    except ValueError:
        return links[0]
    heights = [(int(l.get("height") or 0), i) for i, l in enumerate(links)]
    exact = next((links[i] for h, i in heights if h == target), None)
    if exact:
        return exact
    lower = [(h, i) for h, i in heights if 0 < h < target]
    if lower:
        return links[max(lower)[1]]
    return links[0]


async def _execute_aria2(row: dict):
    """平台下载：调平台直链解析 API → 推荐地址交给 aria2c（RPC）下载并跟踪进度。"""
    from app.services import aria2_service
    from app.platforms import registry
    from app.services import account_manager

    download_id = row["download_id"]
    platform = row.get("platform") or ""

    async def _fail(message: str):
        _append_log(download_id, f"[{now_iso()}] {message}")
        await download_store.update_download(
            download_id, status="failed", error_message=message, finished_at=now_iso(),
        )

    adapter = registry.get_adapter(platform)
    if adapter is None or not adapter.download_api_implemented:
        return await _fail(f"平台 {platform} 不支持平台下载（未提供直链解析 API）")
    content_id = str(row.get("content_id") or "").strip()
    if not content_id:
        return await _fail("平台下载需要视频 ID（该任务 content_id 为空）")
    account_row = await account_manager.get_account(row.get("account_id") or "")
    if account_row is None:
        return await _fail("平台下载需要来源账号（该条收藏未关联账号或账号已删除）")

    await download_store.update_download(download_id, progress="解析下载直链...")
    try:
        links = await adapter.resolve_download_urls(account_manager.to_context(account_row), content_id)
    except Exception as exc:
        logger.warning("任务 %s 直链解析失败：%s", download_id, exc)
        return await _fail(f"解析下载直链失败：{exc}")

    # 图文（note）：逐张图片 + 文案 txt，落独立子目录
    if any(l.get("kind") == "image" for l in links):
        return await _execute_note(row, links)

    best = _pick_link_by_quality(links, row.get("quality"))
    out_dir = downloads_root() / _category_dir(
        platform, content_id, row.get("title") or "", best)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(row.get("title") or "", content_id, str(best.get("ext") or "mp4"))
    await download_store.update_download(
        download_id, progress=f"已解析直链（{best.get('label') or row.get('quality') or 'auto'}），提交 aria2c 下载...")

    try:
        gid = await aria2_service.add(
            best["url"], out_dir, filename, best.get("headers") or {})
    except Exception as exc:
        return await _fail(f"提交 aria2c 失败：{exc}")
    _aria2_gids[download_id] = [gid]
    _append_log(download_id, f"[{now_iso()}] aria2 gid={gid} 画质={best.get('label')} url={best['url']}")

    async def _progress(text: str):
        await download_store.update_download(download_id, progress=text)

    ok, message = await aria2_service.wait(download_id, gid, on_update=_progress)
    _aria2_gids.pop(download_id, None)
    cur = await download_store.get_download(download_id)
    if cur and cur["status"] in ("canceled", "paused"):
        _append_log(download_id, f"[{now_iso()}] 任务被终止（{cur['status']}）")
        return
    if ok:
        output = out_dir / filename
        await download_store.update_download(
            download_id, status="success", progress="下载完成",
            output_path=str(output), finished_at=now_iso(),
        )
        _append_log(download_id, f"[{now_iso()}] 下载完成：{output}")
        logger.info("平台下载完成 %s：%s", download_id, output)
    else:
        await download_store.update_download(
            download_id, status="failed", output_path=str(out_dir),
            error_message=message or "aria2c 下载失败", finished_at=now_iso(),
        )
        _append_log(download_id, f"[{now_iso()}] 下载失败：{message}")
        logger.warning("平台下载失败 %s：%s", download_id, message)


async def _execute_note(row: dict, links: list[dict]):
    """图文下载：独立子目录，逐张图片提交 aria2c，文案（kind=text）落盘 txt。"""
    from app.services import aria2_service

    download_id = row["download_id"]
    platform = row.get("platform") or ""
    content_id = str(row.get("content_id") or "")
    folder = _safe_name(row.get("title") or "", content_id)
    # 图文多文件：分类目录下再套一层作品子目录（图片序列 + txt）
    first_link = next((l for l in links if l.get("url")), {})
    out_dir = downloads_root() / _category_dir(
        platform, content_id, row.get("title") or "", first_link) / folder
    out_dir.mkdir(parents=True, exist_ok=True)

    for link in links:
        text = str(link.get("text") or "").strip()
        if link.get("kind") == "text" and text:
            (out_dir / f"{folder}.txt").write_text(text + "\n", encoding="utf-8")
            _append_log(download_id, f"[{now_iso()}] 文案已保存：{folder}.txt")
            break

    image_links = [l for l in links if l.get("kind") == "image" and l.get("url")]
    if not image_links:
        await download_store.update_download(
            download_id, status="failed", output_path=str(out_dir),
            error_message="图文无可用图片链接", finished_at=now_iso())
        return

    await download_store.update_download(
        download_id, progress=f"图文共 {len(image_links)} 张，提交 aria2c 下载...")
    entries: list[tuple[str, str]] = []  # (gid, filename)
    try:
        for idx, link in enumerate(image_links, start=1):
            filename = f"{idx:02d}.{link.get('ext') or 'jpeg'}"
            gid = await aria2_service.add(
                link["url"], out_dir, filename, link.get("headers") or {})
            entries.append((gid, filename))
            _append_log(download_id, f"[{now_iso()}] aria2 gid={gid} {link.get('label')} -> {filename}")
    except Exception as exc:
        for gid, _ in entries:
            aria2_service.remove(gid)
        message = f"提交 aria2c 失败：{exc}"
        _append_log(download_id, f"[{now_iso()}] {message}")
        await download_store.update_download(
            download_id, status="failed", output_path=str(out_dir),
            error_message=message, finished_at=now_iso())
        return

    _aria2_gids[download_id] = [gid for gid, _ in entries]
    ok_count, errors = 0, []
    for i, (gid, filename) in enumerate(entries, start=1):
        async def _progress(text: str, i=i):
            await download_store.update_download(
                download_id, progress=f"图片 {i}/{len(entries)}：{text}")

        ok, message = await aria2_service.wait(download_id, gid, on_update=_progress)
        if ok:
            ok_count += 1
            continue
        cur = await download_store.get_download(download_id)
        if cur and cur["status"] in ("canceled", "paused"):
            _aria2_gids.pop(download_id, None)
            _append_log(download_id, f"[{now_iso()}] 任务被终止（{cur['status']}）")
            return
        errors.append(f"{filename}: {message or '下载失败'}")
    _aria2_gids.pop(download_id, None)

    if ok_count == len(entries):
        await download_store.update_download(
            download_id, status="success", progress=f"图文下载完成（{ok_count} 张）",
            output_path=str(out_dir), finished_at=now_iso(),
        )
        _append_log(download_id, f"[{now_iso()}] 图文下载完成：{out_dir}（{ok_count} 张）")
        logger.info("图文下载完成 %s：%s（%d 张）", download_id, out_dir, ok_count)
    else:
        message = f"{ok_count}/{len(entries)} 张成功；" + "；".join(errors)[:400]
        await download_store.update_download(
            download_id, status="failed", output_path=str(out_dir),
            error_message=message, finished_at=now_iso(),
        )
        _append_log(download_id, f"[{now_iso()}] 图文下载失败：{message}")
        logger.warning("图文下载失败 %s：%s", download_id, message)


async def terminate(download_id: str) -> bool:
    """终止正在执行的子进程（状态由调用方决定：暂停或取消）。"""
    proc = _running.get(download_id)
    if proc is None:
        return _remove_aria2_tasks(download_id)
    proc.kill()
    return True


def _remove_aria2_tasks(download_id: str) -> bool:
    """移除该任务登记的全部 aria2 下载（视频单 gid / 图文多 gid）。"""
    from app.services import aria2_service

    gids = _aria2_gids.get(download_id)
    if not gids:
        return False
    _aria2_gids.pop(download_id, None)
    return any(aria2_service.remove(gid) for gid in gids)


async def cancel(download_id: str) -> bool:
    """取消正在执行的任务（标记 canceled 并杀掉子进程）。"""
    proc = _running.get(download_id)
    if proc is None:
        return _remove_aria2_tasks(download_id)
    await download_store.update_download(
        download_id, status="canceled", progress="已取消", finished_at=now_iso()
    )
    proc.kill()
    return True
