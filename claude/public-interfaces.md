# 对外接口

REST API 前缀统一 `/api/v1`，交互式文档 `http://127.0.0.1:8300/docs`。无鉴权（仅本地监听）。

## 平台

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/platforms` | 平台元信息：implemented / supported_actions / api_fetch_implemented / **follows_api_implemented** / api_operations / icon_url |
| POST | `/platforms/reload` | 重扫声明式平台目录（热加载） |
| GET | `/platforms/{platform}/icon` | 平台图标文件 |

## 账号（/accounts）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET / POST | `/accounts` | 列表（含 logging_in、avatar）/ 创建(201) |
| GET / PATCH / DELETE | `/accounts/{id}` | 详情 / 改名启停 / 删除（级联 favorites+profile） |
| GET | `/accounts/{id}/avatar` | 本地化账号头像 |
| POST | `/accounts/{id}/login` | 202 后台扫码，返回 poll_url；重复 409 |
| POST | `/accounts/{id}/login/close` | 关闭登录浏览器 |
| GET | `/accounts/{id}/status?refresh=` | 登录态检查（可回填身份） |
| POST / GET | `/accounts/{id}/browse` | 手动浏览窗口 开关(toggle) / 查询 |
| GET | `/accounts/{id}/cookies` | 读 profile cookie 存快照 |
| POST | `/accounts/{id}/wechat-import` | 上传微信收藏 JSON（≤100MB） |
| POST | `/accounts/{id}/refresh-profile`、`/accounts/refresh-profile` | 单个 / 批量身份刷新（未实现平台 501） |
| POST | `/accounts/{id}/folders/edit`、`/folders/del` | B 站收藏夹编辑 / 删除 |
| POST | `/accounts/{id}/operations/{op_id}` | 平台写操作（同步） |
| POST | `/accounts/{id}/operations/{op_id}/stream` | 写操作 SSE 流式 |

## 抓取

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/fetch` | body `{platform, account_id, action, params?, async_run?}`；默认同步 200，`async_run=true` 202+task_id。响应 `result_count / new_favorites / cursor / has_more / items(≤100)` |
| POST | `/fetch/stream` | SSE：事件 `task / items / done / error` |

params 通用：`count`、`cursor`（增量翻页）、`date_from/date_to`（收藏时间窗口）、`method`（browser/api）。平台专属：bilibili 指定收藏夹/他人 mid、wechat `json_path`。

## 查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stats` | 仪表盘统计（账号/收藏/任务/磁盘体积，体积缓存 300s） |
| GET / DELETE | `/tasks`、`/tasks/{id}` | 任务列表 / 详情 / 清空 |
| GET | `/favorites` | 多维过滤：account/platform/tag/folder/author/日期区间/发布日期区间/tags(OR)/q/limit≤5000/offset |
| GET | `/favorites/facets` | 过滤面板候选（账号/收藏夹/作者） |
| POST / DELETE | `/favorites/batch-delete`、`/favorites?account_id=` | 批量删关系（contents 保留）/ 按账号清空 |
| GET | `/tags` | 标签聚合 + 分组（「其他」兜底） |

## 特别关注（/follows，2026-09-19 新增）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET / POST | `/follows/authors` | 博主列表（含未读数+分组）/ 添加博主 |
| PATCH / DELETE | `/follows/authors/{sec_uid}` | 更新（分组/昵称/头像/粉丝数）/ 删除（清资产） |
| GET | `/follows/authors/{sec_uid}/avatar` | 本地化头像文件 |
| GET | `/follows/following/{account_id}` | 实时拉取账号关注列表（只读，count 0=全部） |
| GET | `/follows/authors/{sec_uid}/posts` | 博主主页作品分页（cursor 兼容 int\|str，末页归 0） |
| GET | `/follows/authors/{sec_uid}/posts/{content_id}/cover` | 缩略图：本地文件或 307 跳媒体代理并顺手入队本地化 |
| GET | `/follows/aweme/{aweme_id}` | 播放信息（直链/图文原图/作者/统计/music_url/iframe_url） |
| POST / DELETE | `/follows/read/{content_id}` | 标记 / 取消已读 |
| POST | `/follows/sync` | 一键同步最新作品入库（source='特别关注'） |
| POST | `/follows/sync/stream` | SSE 流式同步（progress/done/error），前端 Header 按钮实时进度 |
| GET | `/follows/media?url=` | CDN 媒体流式代理（UA/referer/cookie/代理按域注入，Range 透传） |

## 定时 / 下载 / 设置 / 标签 / AI / 封面 / 通知

| 分组 | 接口 |
|------|------|
| `/schedules` | GET / POST / PATCH `/{id}` / DELETE `/{id}` / POST `/{id}/trigger`(202，防重入) |
| `/downloads` | GET / POST(幂等) / `/{id}/retry` / `/{id}/pause` / `/{id}/reveal`(打开文件管理器) / DELETE `/{id}` |
| `/settings` | GET / PUT（download_dir 校验）；`/avatar` GET/POST(≤5MB) |
| 标签 | DELETE `/tags/{tag}?delete_favorites=`、GET `/tags/{tag}/usage`、POST `/tag-groups`、PUT `/tag-groups/{name}`、PUT `/contents/{id}/tags`（≤10 个） |
| `/ai/agents` | CRUD + POST `/{id}/test`（连通性，返回 ok/latency_ms/reply） |
| `/ai/tag/stream` | POST SSE 批量打标：事件 `task / batch / done / error` |
| `/covers` | 收藏封面本地化下发 |
| `/notifications` | 应用内通知 |

## Web 界面

`GET /` 托管 `web/dist`（React SPA，HashRouter）。未构建时返回提示页。页面与路由详见 [web/CLAUDE.md](../web/CLAUDE.md)。

## 内部扩展接口（代码级）

- `BasePlatformAdapter`：login / check_login_status / fetch_favorites 必须实现；fetch_favorites_api / execute_api_operation / refresh_profile 可选。
- `registry.register(adapter)`：注册后 /platforms、账号创建、action 校验、操作表单自动生效。
- `DeclarativeAdapter(spec, base_dir)`：JSON 声明式平台，spec 字段见 `app/platforms/declarative.py`。
