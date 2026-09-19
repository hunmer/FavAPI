"""FastAPI 应用工厂与实例。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import accounts, agents, ai_tag, covers, downloads, fetch, follows, notifications, queries, schedules, settings, tags
from app.database import db
from app.services import aria2_service, cover_worker, download_store, download_worker, scheduler, data_store
from app.web.router import mount_web

# 让 favapi.* 调试日志输出到 stderr（procm 会同时采集 stdout/stderr）
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    # 清理上次进程残留的运行态（重启/崩溃后无人执行，且会卡住调度器防重入与下载队列）
    stale_tasks = await data_store.interrupt_stale_tasks()
    stale_downloads = await download_store.requeue_stale_running()
    if stale_tasks or stale_downloads:
        logging.getLogger("favapi").info(
            "启动清理：%d 个中断任务标记失败，%d 个下载重新入队", stale_tasks, stale_downloads)
    await scheduler.start()
    await download_worker.start()
    await cover_worker.start()
    yield
    await cover_worker.stop()
    await download_worker.stop()
    await aria2_service.shutdown()
    await scheduler.stop()
    await db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="FavAPI",
        description="多平台个人收藏抓取 HTTP API 服务（Douyin 完整实现 + Bilibili 占位）",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(accounts.router)
    app.include_router(accounts.platforms_router)
    app.include_router(agents.router)
    app.include_router(ai_tag.router)
    app.include_router(covers.router)
    app.include_router(downloads.router)
    app.include_router(fetch.router)
    app.include_router(follows.router)
    app.include_router(notifications.router)
    app.include_router(queries.router)
    app.include_router(schedules.router)
    app.include_router(settings.router)
    app.include_router(tags.router)
    mount_web(app)
    return app


app = create_app()
