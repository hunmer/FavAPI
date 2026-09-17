# 依赖与配置

## 运行依赖（requirements.txt，无版本锁定）

| 包 | 用途 |
|----|------|
| fastapi / uvicorn[standard] | Web 框架 / ASGI（含 python-multipart 支持上传） |
| aiosqlite | 异步 SQLite（单连接 + WAL） |
| playwright | Chromium 持久化 profile 自动化（首次需 install chromium） |
| httpx | 冒烟测试 ASGITransport、部分 HTTP 请求 |
| croniter | 定时计划 cron 表达式解析 |
| curl_cffi | API 直连通道：模拟 Chrome TLS/HTTP2 指纹（httpx 会被部分平台识别返回空响应） |
| xhshow | 小红书 x-s / x-s-common 请求签名纯算 |
| yt-dlp | 下载器之一（子进程调用，可注入 Netscape cookie） |

外部运行时依赖：videodl（下载器之二，可选）；Node ≥16（快手 `__NS_hxfalcon` 签名经 `sig_vm.js` + `sig4.cjs` 离线生成）。

无 pyproject.toml / lock 文件。Python 3.13（`.venv`）。

## 环境变量（app/config.py）

| 变量 | 默认 | 说明 |
|------|------|------|
| `FAVAPI_HOST` / `FAVAPI_PORT` | 127.0.0.1 / 8300 | HTTP 监听 |
| `FAVAPI_DATA_DIR` | `<根>/data` | 数据库/profile/下载/上传根目录；测试隔离用 |
| `FAVAPI_PLATFORMS_DIR` | `<根>/platforms` | 声明式平台目录 |
| `FAVAPI_HEADLESS` | 0（有头） | 抓取/登录是否无头；平台检测严格，保持 0 |

前端相关（web/）：`FAVAPI_BACKEND`（dev 代理目标，默认 http://127.0.0.1:8300）、`REACT_EDITOR`（DevInspector 打开源码的编辑器命令，默认 `code`）。

## 常量（config.py）

`LOGIN_TIMEOUT=300s`、`FETCH_TIMEOUT=300s`、`MAX_CONCURRENT_BROWSERS=2`、`PAGE_TIMEOUT=30000ms`、`DB_PATH=DATA_DIR/favapi.db`、`PROFILES_DIR=DATA_DIR/profiles`。

## 运行时配置文件

| 文件 | 内容 |
|------|------|
| `data/settings.json` | profile_path / headless / request_interval / request_timeout / download_dir / download_concurrency（前端设置页可改，app_settings.py 读写） |
| `platforms/<name>/platform.json` | 声明式平台 spec：home_url / login_cookies(+mode any\|all) / proxy(auto\|url\|env) / capture(url_contains、page_url 支持 {userId}、items_path 支持 a.b[].c、has_more 哨兵) / fields 映射 / scripts 页面与子进程钩子 |
| `procm-commands.json` | procm 持久化进程命令（Win/mac 双套 + web） |

## 数据目录布局（data/，git 忽略）

`favapi.db`、`profiles/<platform>_<account_id>/`、`downloads/<platform>/`、`uploads/`（头像、账号头像）、`wechat_imports/{id}/messages.json`、`downloads/.cookies/{id}.cookies.txt`（yt-dlp 注入用）。

## 平台常量速查

- douyin：拦截 `/aweme/v1/web/aweme/listcollection`，登录 cookie `sessionid`；MAX_COUNT=500。
- xiaohongshu：拦截 `/api/sns/web/v2/note/collect/page`，登录判定用 DOM 判据而非 cookie。
- youtube：登录 cookie SID/SAPISID/__Secure-3PSID/LOGIN_INFO，解析 playlist?list=LL。
- kuaishou：登录 cookie mode=all；{userId} 预导航拦截取 eid。
- 各平台 `constants.py` 为调参热点。
