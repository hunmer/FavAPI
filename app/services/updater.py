"""便携包自动更新（tufup / TUF）。

仅 frozen（PyInstaller 便携包）启用：启动时后台线程 refresh 元数据 →
发现新版本 → 下载（优先增量补丁）→ 安装 → 通过回调让主流程优雅退出并重启。
任何失败只记日志，绝不影响当前版本运行。

安装策略（按平台）：
- macOS：purge 安装目录（排除 data/、platforms/、pw-browsers/ 用户数据），
  copytree(symlinks=True) 保留 chromium .app 内的符号链接；安装后由 on_update_ready
  优雅退出并重启。
- Windows：运行中的 exe 无法覆盖，复用 tufup 的 robocopy 批处理方案（进程退出后
  搬运文件），批处理完成搬运后自动拉起新实例；本进程立即优雅退出。
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

from app import version

logger = logging.getLogger("favapi.updater")

# 安装目录中不参与更新替换的用户数据/资源目录（macOS purge 排除项）
_KEEP_DIRS = ("data", "platforms", "pw-browsers")

# Windows 批处理模板：tufup 默认模板 + 搬运完成后启动新实例 + 自删除
_WIN_BATCH_TEMPLATE = """@echo off
echo Moving app files...
robocopy "{src_dir}" "{dst_dir}" {robocopy_options}
echo Restarting FavAPI...
start "" "{dst_dir}\\FavAPI.exe"
echo Done.
(goto) 2>nul & del "%~f0"
"""


def app_name() -> str:
    if sys.platform == "darwin":
        return "FavAPI-macos-arm64"
    return "FavAPI-windows-x64"


def _frozen_dirs() -> tuple[Path, Path]:
    """返回 (安装目录, 打包内可信元数据目录)。"""
    install_dir = Path(sys.executable).resolve().parent
    metadata_dir = install_dir / "_internal" / "tuf-metadata"
    return install_dir, metadata_dir


def start_background_check(on_update_ready) -> None:
    """启动后台更新检查。on_update_ready(new_version) 在安装就绪后由本线程调用，
    负责优雅退出（停服务、关窗口）；重启动作见模块 docstring 的平台策略。"""
    if not getattr(sys, "frozen", False):
        return  # 源码运行不检查更新
    if os.environ.get("FAVAPI_NO_UPDATE") == "1":
        logger.info("FAVAPI_NO_UPDATE=1，跳过自动更新检查")
        return
    from app import config

    def _worker():
        try:
            _check_and_apply(config, on_update_ready)
        except Exception:
            logger.exception("自动更新失败，继续以当前版本运行")

    import threading

    threading.Thread(target=_worker, name="tufup-updater", daemon=True).start()


def _check_and_apply(config, on_update_ready) -> None:
    from tufup.client import Client

    install_dir, metadata_dir = _frozen_dirs()
    cache_dir = Path(config.DATA_DIR) / "update-cache"
    # tufup Client 不会自建目录，缺目录会在下载时 FileNotFoundError
    (cache_dir / "targets").mkdir(parents=True, exist_ok=True)
    (cache_dir / "extract").mkdir(parents=True, exist_ok=True)
    client = Client(
        app_name=app_name(),
        app_install_dir=install_dir,
        current_version=version.__version__,
        metadata_dir=metadata_dir,
        metadata_base_url=config.UPDATE_METADATA_URL,
        target_dir=cache_dir / "targets",
        target_base_url=config.UPDATE_TARGETS_URL,
        extract_dir=cache_dir / "extract",
        refresh_required=False,
    )
    # 注意：check_for_updates 内部自带 refresh，不可再显式调用 refresh()，
    # 否则触发 tuf ngclient "Cannot update timestamp after snapshot" 状态机异常
    new_meta = client.check_for_updates()
    if not new_meta:
        logger.info("已是最新版本 %s", version.__version__)
        return
    logger.info("发现新版本 %s → %s，开始下载安装", version.__version__, new_meta.version)
    client.download_and_apply_update(
        skip_confirmation=True,
        install=_make_installer(on_update_ready),
        purge_dst_dir=(sys.platform == "darwin"),  # Windows 的 /xf 无法排除目录，不 purge
        exclude_from_purge=list(_KEEP_DIRS),
    )


def _make_installer(on_update_ready):
    def _install(src_dir, dst_dir, **kwargs):
        if sys.platform == "darwin":
            _install_mac(src_dir, dst_dir, **kwargs)
            on_update_ready()
        else:
            _install_win(src_dir, dst_dir, **kwargs)
            on_update_ready()  # 批处理在进程退出后接管搬运与重启
    return _install


def _install_mac(src_dir, dst_dir, exclude_from_purge=None, **kwargs) -> None:
    import shutil

    from tufup.utils import remove_path

    dst = Path(dst_dir)
    keeps = {dst / name for name in (exclude_from_purge or [])}
    for path in dst.iterdir():
        if path not in keeps:
            remove_path(path=path)
    # symlinks=True：chromium .app 内部为相对符号链接，解引用复制会破坏结构；
    # pw-browsers 已被 purge 排除（用户数据），复制时也须忽略——其内部的
    # Versions/Current 等符号链接与现存文件冲突（Errno 17），且 chromium 不随增量更新
    shutil.copytree(
        src_dir, dst, dirs_exist_ok=True, symlinks=True,
        ignore=shutil.ignore_patterns("pw-browsers"),
    )
    logger.info("macOS 更新文件已就位：%s", dst)


def _install_win(src_dir, dst_dir, **kwargs) -> None:
    from tufup.utils.platform_specific import _install_update_win

    logger.info("Windows 更新将退出后由批处理完成文件替换")
    try:
        _install_update_win(
            src_dir=src_dir,
            dst_dir=dst_dir,
            purge_dst_dir=False,
            exclude_from_purge=None,
            batch_template=_WIN_BATCH_TEMPLATE,
            process_creation_flags=subprocess.CREATE_NO_WINDOW,
            **{k: v for k, v in kwargs.items() if k not in ("purge_dst_dir", "exclude_from_pure")},
        )
    except SystemExit:
        pass  # tufup 默认安装器会 sys.exit，后台线程中无害，吞掉后继续回调
