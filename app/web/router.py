"""Web 控制台静态托管：服务 web/ 前端构建产物（vite build → web/dist）。"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("favapi.web")

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

_NO_BUILD_PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>FavAPI Web Console</title><body style="font-family:system-ui;padding:40px;line-height:1.8">
<h2>Web 控制台尚未构建</h2>
<p>请先执行：<code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code>，然后刷新本页。</p>
<p>开发模式可运行 <code>cd web &amp;&amp; npm run dev</code>（vite 已配置 /api 代理到本地后端）。</p>
<p>API 文档：<a href="/docs">/docs</a></p></body></html>"""


def mount_web(app: FastAPI):
    """挂载前端静态资源；dist 不存在时给出构建提示页。"""
    if (DIST_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="web")
    else:
        logger.warning("web/dist 不存在，Web 控制台未挂载（先执行 cd web && npm run build）")

        @app.get("/", include_in_schema=False)
        async def _no_build():
            return HTMLResponse(_NO_BUILD_PAGE)
