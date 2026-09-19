---
name: favapi-cli
description: 通过命令行（cli.py）调用 FavAPI 各平台 API 的操作指南。当用户想用 CLI / 命令行 / 脚本抓取收藏、查询平台数据、执行点赞/取消收藏/解析下载直链等平台操作，或提到 favapi 命令行、python cli.py、脚本化批量操作、定时同步时使用——即使用户只说"帮我抓一下收藏"或"用命令行查"。
---

# FavAPI CLI 指南

`cli.py` 是 FavAPI 的命令行入口（项目根目录），不依赖服务运行，直接调用各平台 adapter 的 API，共用同一 SQLite 数据与浏览器登录态。适合脚本化、批处理、无 Web 界面环境。

## 前置条件

- 用项目虚拟环境的 Python 执行：`.venv/Scripts/python.exe cli.py ...`（Windows）或 `.venv/bin/python cli.py ...`（macOS/Linux）
- 操作真实账号前，账号需已通过 Web 界面扫码登录（`cli.py accounts` 可查状态）
- 浏览器模拟抓取（method=browser，默认）需要 playwright chromium 已安装；API 直连（method=api）不需要

## 命令速查

```bash
cli.py platforms                  # 列出各平台可用的抓取目标(fetch)与 API 操作(op)，含参数名
cli.py platforms --json           # 完整定义（参数 label/type/help/options，供构造调用）
cli.py accounts                   # 列出账号：account_id / platform / status / 名称
cli.py accounts --json            # 含 extra（头像、收藏夹等）
cli.py fetch <account_id> [action] [-p k=v ...]   # 抓取入库（action 缺省 = 平台首个抓取目标）
cli.py op <account_id> <op_id> [-p k=v ...]       # 执行平台 API 操作，结果 JSON 输出
```

先 `platforms` 查可用 action / op_id 和参数名，再 `accounts` 拿 account_id，最后组装调用。**不要凭记忆猜 op_id 或参数名**——各平台能力差异大，以 `platforms` 输出为准。

## 参数规则

- `-p k=v` 可重复传入，值自动转 int / bool（`-p count=20` → 20，`-p flag=true` → True），其余按字符串
- 通用参数：`count`（0=全部）、`cursor`（翻页续抓）、`date_from`/`date_to`（收藏日期区间）、`method`（browser/api，仅 fetch）

## 常见任务

```bash
# 查收藏（只读，不写库）
cli.py op acc_xxx list_favorites -p count=20

# 抓取收藏入库（长任务，stderr 实时输出 [进度] 行，stdout 输出汇总 JSON）
cli.py fetch acc_xxx -p count=50 -p method=api

# 抖音喜欢列表 / 稍后再看 / 观看历史
cli.py op acc_xxx list_likes -p count=20
cli.py op acc_xxx list_watchlater
cli.py op acc_xxx list_history -p count=10

# 解析下载直链（配合 aria2c/yt-dlp 使用）
cli.py op acc_xxx resolve_download_urls -p aweme_id=7686537195435632817

# 写操作示例（小红书点赞 / 收藏笔记）
cli.py op acc_xxx like_note -p note_oid=xxx
cli.py op acc_xxx collect_note -p note_id=xxx
```

## 输出与退出码

- 结果 JSON 打到 **stdout**（`ensure_ascii=False, indent=2`），可直接管道给 `jq` 等处理
- fetch 的进度行（`[进度] 已抓取 N 条`）打到 **stderr**，不污染 stdout
- 失败时错误信息打到 stderr，退出码非 0；脚本里可用 `$?` / `$LASTEXITCODE` 判断

## 注意事项

- `platforms` 输出中标注 `[危险]` 的操作（批量取消收藏/点赞等）是**不可逆写操作**，执行前向用户确认
- CLI 与运行中的服务共用数据库和浏览器 profile，避免同时对同一账号发起抓取
- fetch 走 `/api/v1/fetch` 同一任务管线（校验→抓取→入库→任务记录），响应含 `cursor`/`has_more` 供增量续抓；`op` 是纯 API 调用不建任务
- 登录态失效时账号会被标记 expired（HTTP 409 同义），提示用户在 Web 界面重新扫码
- `action=ai_tag` 是特殊虚拟 action（AI 打标管线），仅 fetch 支持
