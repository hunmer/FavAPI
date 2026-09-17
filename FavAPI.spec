# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：构建便携包（onedir）。

用法：scripts/build_portable.sh（自动调用本文件）
产物：dist/FavAPI/  —— 可执行文件 + _internal 依赖，运行还需 build_portable.sh
补齐包外的 platforms/ 与 pw-browsers/。
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("web/dist", "web/dist"),
]
# kuaishou 签名脚本（node 运行时资源，api_client 以 __file__ 相对路径调用）
datas += collect_data_files("app.platforms.kuaishou", includes=["*.js", "*.cjs"])
# xhshow 无 PyInstaller hook，全量收集子模块与数据
datas += collect_data_files("xhshow")

hiddenimports = [
    # main.py 通过字符串 "app.server:app" 延迟导入，静态分析不可见
    "app.server",
    # uvicorn 运行期按配置动态导入的模块（uvicorn[standard] 全量）
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
] + collect_submodules("xhshow")
# playwright / yt-dlp / curl_cffi 由包自带的 __pyinstaller__ hook 处理

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FavAPI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 服务进程保留控制台输出日志
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="FavAPI",
)
