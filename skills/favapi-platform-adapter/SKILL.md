---
name: favapi-platform-adapter
description: 为 FavAPI 创建新平台适配器，优先使用声明式 platform.json，必要时实现 Python BasePlatformAdapter；说明平台目录结构、字段映射、代理与分页配置，以及生产环境导入、启动扫描和 /api/v1/platforms/reload 激活流程。用于新增收藏平台、接入 Threads 等自定义平台、部署或排查平台热加载。
---

# FavAPI 平台适配器

## 先选择实现方式

- 页面能触发 JSON 接口且字段稳定：使用声明式适配器。
- 需要签名算法、复杂分页、特殊登录或多接口合并：实现 Python 适配器。
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

代理：`proxy: "auto"`（默认）读取 `HTTPS_PROXY/HTTP_PROXY`，Windows 再读取 Internet Settings；也可填 URL 或 `{server, username, password}`。

## Python 适配器

在 `app/platforms/<platform>/adapter.py` 继承 `BasePlatformAdapter`，实现 `login`、`check_login_status`、`fetch_favorites`，返回 `FetchResult(items=...)`。在 `registry.py` 导入并 `register(Adapter())`；复杂解析逻辑放同目录 `parser.py`。

## 本地验证

```powershell
python -m compileall app
Invoke-RestMethod "http://127.0.0.1:8300/api/v1/platforms"
Invoke-RestMethod -Method Post "http://127.0.0.1:8300/api/v1/platforms/reload"
```

确认平台 `implemented=true`、包含 `list_favorites`，再创建账号并用真实 profile 登录。检查任务返回的 `items`、`cursor`、`has_more`。

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
