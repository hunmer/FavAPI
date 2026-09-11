---
name: favapi-platform-adapter
description: 为 FavAPI 创建新平台适配器，优先使用声明式 platform.json，必要时实现 Python BasePlatformAdapter；说明平台目录结构、字段映射、代理与分页配置，以及生产环境导入、启动扫描和 /api/v1/platforms/reload 激活流程。用于新增收藏平台、接入 Threads 等自定义平台、部署或排查平台热加载。
---

# FavAPI 平台适配器

## 先选择实现方式

- 页面能触发 JSON 接口且字段稳定：使用声明式适配器。
- 需要签名算法、复杂分页、特殊登录或多接口合并：实现 Python 适配器。
- 页面展示的是登录后动态内容（例如 YouTube `feed/playlists` / `playlist?list=LL`），且接口返回 401、结构不稳定或只返回分组时：优先用已登录浏览器打开页面，从 DOM 提取 ID/条目，再调用专用接口或外部工具获取详情；不要假设页面 URL 可以直接交给外部工具。
- 不修改现有 bilibili、xiaohongshu、douyin 行为；先用独立目录验证。

## 声明式适配器（推荐）

创建目录：

```text
platforms/<platform>/platform.json
```

最小配置：

```json
{
  "platform": "threads",
  "display_name": "Threads",
  "home_url": "https://www.threads.com/saved",
  "login_cookies": ["sessionid", "csrftoken"],
  "proxy": "auto",
  "supported_actions": ["list_favorites"],
  "capture": {
    "url_contains": "/graphql/query",
    "items_path": "data.items[].post",
    "cursor_path": "data.page_info.end_cursor",
    "has_more_path": "data.page_info.has_next_page",
    "fields": {
      "content_id": "pk",
      "title": "caption.text",
      "author_name": "user.username"
    }
  }
}
```

字段规则：`items_path` 使用点路径，数组节点加 `[]`；`fields` 左侧为通用 content 字段，右侧为响应对象路径。可配置 `headers`、`wait_ms`、`max_rounds`、`scroll_step`、`scroll_wait_ms`。

需要自定义脚本时，在同一平台目录内放置脚本并在 JSON 声明：

```json
"scripts": {
  "before_login_js": "prepare.js",
  "after_fetch_page_js": "expand.js",
  "before_fetch_python": "sign_request.py",
  "python_timeout": 30
}
```

JS 脚本在页面上下文执行，接收 `{account_id, params}` 参数；Python 脚本以当前 Python 解释器启动，从 stdin 接收 JSON（含 `account_id`、`platform`、`params`），工作目录为平台目录。支持阶段：`before_login_js`、`after_login_page_js`、`before_fetch_js/python`、`after_fetch_page_js/python`。脚本路径必须位于平台目录内，非零退出或超时会使任务失败。

代理：`proxy: "auto"`（默认）读取 `HTTPS_PROXY/HTTP_PROXY`，Windows 再读取 Internet Settings；也可填 URL 或 `{server, username, password}`。

### 动态页面与外部工具实践

- 先确认页面语义：`feed/playlists` 可能展示播放列表分组，`playlist?list=LL` 才是“喜欢的视频”条目；抓取 URL、字段和内容类型必须与页面实际展示一致。
- 浏览器 DOM 抓取应等待 `domcontentloaded` 后再等待异步渲染，并通过滚动触发懒加载；使用稳定选择器（元素 ID、组件标签、`content-id-*` 等），不要依赖经常变化的 CSS 哈希类名。
- 图片字段可能在 `currentSrc`、`src`、`data-src` 或 `srcset`，应按优先级读取；仍为空时可使用内容 ID 构造平台稳定缩略图 URL作为兜底。
- 若复用 `yt-dlp` 等外部工具，先由浏览器解析需要登录的页面，再将具体条目 URL 交给工具；记录可执行文件、参数、返回码和 stderr 摘要。不要把 Cookie 值写入日志。
- 账号 Cookie 快照转换为 Netscape 文件时保留 `secure` 属性，并按平台域名过滤；YouTube 通常需要同时保留 `youtube.com` 与 `google.com` 域名 Cookie。Cookie 仅存在不代表外部工具一定能通过认证，仍需用真实命令验证。
- 流式抓取中必须在“加入列表”和触发 `on_batch` 之前执行 `count` 限制；最后再裁剪只能限制 `FetchResult`，无法撤回已经入库或推送的超额条目。

## Python 适配器

在 `app/platforms/<platform>/adapter.py` 继承 `BasePlatformAdapter`，实现 `login`、`check_login_status`、`fetch_favorites`，返回 `FetchResult(items=...)`。在 `registry.py` 导入并 `register(Adapter())`；复杂解析逻辑放同目录 `parser.py`。

专用适配器若使用平台目录资源（如 `icon`），应提供 `base_dir` 并在注册时传入实际平台目录；否则 `/api/v1/platforms/<platform>/icon` 无法定位文件。声明式适配器可直接在 `platform.json` 配置 `icon`，文件必须位于同一平台目录。

## 本地验证

```powershell
python -m compileall app
Invoke-RestMethod "http://127.0.0.1:8300/api/v1/platforms"
Invoke-RestMethod -Method Post "http://127.0.0.1:8300/api/v1/platforms/reload"
```

确认平台 `implemented=true`、包含 `list_favorites`，再创建账号并用真实 profile 登录。检查任务返回的 `items`、`cursor`、`has_more`。

涉及浏览器或外部工具的平台还应执行一次真实小数量抓取（例如 `count=1` 或 `count=20`），核对日志中的页面 URL、发现条目数量、工具返回码、Cookie 名称（不含值）和最终入库数量；不要只以“登录成功”判断抓取链路可用。

## 生产导入与激活

1. 将平台子目录复制到生产 `FAVAPI_PLATFORMS_DIR`（未设置时为项目根 `platforms/`）。
2. 校验 JSON UTF-8、`platform` 唯一且路径为 `<name>/platform.json`。
3. 若使用代理，设置 `HTTPS_PROXY` 或确认 Windows 系统代理；敏感认证信息不要提交仓库。
4. 重启服务以执行启动扫描；运行中可调用 `POST /api/v1/platforms/reload`，无需重启。
5. 通过 `GET /api/v1/platforms` 验证已激活，再创建账号执行一次小数量抓取。
6. 声明错误只记录 warning，不应阻断其他平台；查看服务日志定位文件路径和异常。

热加载会覆盖同名平台实例；删除 JSON 后需重启服务才能移除已注册实例。生产环境应先在灰度目录验证，再替换正式目录。

## 安全与兼容性

不要在 JSON 提交 cookies、sessionid 或代理密码。遵守目标平台条款与速率限制。字段缺失应允许返回空值；`content_id` 缺失的条目会被丢弃。
