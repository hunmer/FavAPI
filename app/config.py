"""全局配置：路径、服务参数、浏览器行为。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录（数据库 + 浏览器 profile），可用环境变量覆盖（测试用）
DATA_DIR = Path(os.environ.get("FAVAPI_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "favapi.db"
PROFILES_DIR = DATA_DIR / "profiles"
PLATFORMS_DIR = Path(os.environ.get("FAVAPI_PLATFORMS_DIR", str(BASE_DIR / "platforms")))

# HTTP 服务
HOST = os.environ.get("FAVAPI_HOST", "127.0.0.1")
PORT = int(os.environ.get("FAVAPI_PORT", "8300"))

# 浏览器：抖音对无头模式检测严格，默认有头
HEADLESS = os.environ.get("FAVAPI_HEADLESS", "0") == "1"
LOGIN_TIMEOUT = 300          # 扫码登录最长等待（秒）
FETCH_TIMEOUT = 300          # 单次抓取整体超时（秒）
MAX_CONCURRENT_BROWSERS = 2  # 全局并发浏览器上限
PAGE_TIMEOUT = 30_000        # Playwright 默认超时（毫秒）
