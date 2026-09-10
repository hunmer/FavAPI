"""FastAPI 应用工厂与实例。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import accounts, fetch, queries
from app.database import db
from app.web.router import router as web_router

# 让 favapi.* 调试日志输出到 stderr（procm 会同时采集 stdout/stderr）
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
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
    app.include_router(fetch.router)
    app.include_router(queries.router)
    app.include_router(web_router)
    return app


app = create_app()
