"""本地一键启动：python main.py"""
import sys

# Windows 下 stderr 默认 GBK，会导致日志中文在 procm 等采集端乱码
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import uvicorn

from app import config

if __name__ == "__main__":
    uvicorn.run("app.server:app", host=config.HOST, port=config.PORT)
