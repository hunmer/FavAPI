# 平台收藏抓取「API 请求」模式接入指南

> 背景：FavAPI 各平台的收藏抓取原本只有「浏览器模拟」一种方式（起 Chromium → 滚动页面 → 拦截 XHR 响应），单页 20 条要 3~5 秒，全量抓取动辄数分钟。
> 2026-09 抖音平台率先落地了「API 请求」直连模式（curl-impersonate 模拟 Chrome 指纹 + profile cookies 直连接口），39 条收藏 3.8 秒拿完，快一个量级。
> 本文档交代原理、通用架构，以及**如何为一个新平台复刻这套流程**：JS Reverse MCP 抓包/逆向分析 → 用户登录 → Python 原型验证 → 落地到 platform 代码。

## 1. 原理：为什么不能直接用 httpx/requests 请求

多数平台（抖音、小红书等）的风控不只看 cookie 和签名，还看**客户端 TLS / HTTP2 指纹**：

| 客户端 | 结果（抖音实测） |
|---|---|
| 浏览器 fetch | ✅ 正常返回 |
| node 原生 https / Python httpx | ❌ HTTP 200 但响应体为空（`Content-Length: 0`） |
| cycletls（自定义 JA3 的 Go uTLS） | ❌ 同样空响应 —— 只模拟 ClientHello 不够 |
| **curl_cffi（curl-impersonate，`impersonate="chrome"`）** | ✅ **完整复刻 Chrome 的 TLS + HTTP2 帧/头部顺序，正常返回** |

**空响应（HTTP 200 + len=0）就是指纹拦截的典型特征**，遇到它不要怀疑 cookies，先换 curl_cffi。

附带结论（抖音 2026-09 实测）：`a_bogus` 签名当前不做强校验（乱码/缺失均可通过），拦截全靠指纹层。其他平台自行验证，不要假设。

## 2. 已落地的通用架构

任何平台想支持 API 模式，只需在现有抽象上做三件事，执行层和前端全部复用：

### 2.1 后端（`app/platforms/`）

- **`base.py`** —— `BasePlatformAdapter` 已内置：
  - `api_fetch_implemented: bool = False`：能力声明，平台覆写为 `True`
  - `resolve_fetch_method(params)`：解析 `params.method`（`browser`/`api`），未实现 api 的平台抛 `ValueError`
  - `fetch_favorites_api()`：API 模式入口，默认 `NotImplementedError`
  - `validate_params()` 默认实现已包含 method 校验
- **`app/services/task_executor.py`** —— `validate_fetch` 里统一调 `adapter.resolve_fetch_method(params)`，
  不支持的平台在提交阶段直接 400（**不要依赖各平台 validate_params 是否调 super**，BilibiliAdapter 覆写时就没调，踩过）
- **`app/platforms/registry.py`** —— `_info` 已输出 `api_fetch_implemented` 字段（`GET /api/v1/platforms` 可查）

请求链路：`POST /api/v1/fetch` → `params.method="api"` → `adapter.fetch_favorites` 开头分发：

```python
async def fetch_favorites(self, account, params, on_batch=None) -> FetchResult:
    if self.resolve_fetch_method(params) == "api":
        return await self.fetch_favorites_api(account, params, on_batch)
    return await self._fetch_favorites_browser(account, params, on_batch)
```

### 2.2 前端（`web/src/`）

- `types.ts`：`ScrapingFormData.method?: 'browser' | 'api'`
- `api.ts`：`formToParams` 已透传 `params.method`
- `data/mockFavData.ts`：`PlatformMeta.apiFetch?: boolean`，支持的平台置 `true`（select 里才会出现「API 请求」选项）
- `components/Accounts/AccountDetail.tsx`：抓取表单已有「执行方式」select（浏览器模拟 / API 请求），按 `platform.apiFetch` 动态出选项

### 2.3 依赖

`requirements.txt` 已加 `curl_cffi`。新环境记得 `pip install -r requirements.txt`。

## 3. 新平台接入流程（四步）

以抖音为参照模板，代码在 `app/platforms/douyin/`（adapter.py / api_client.py / constants.py / parser.py）。

### 第一步：抓包与签名逆向（JS Reverse MCP，不开玩笑，这一步定成败）

用 JS Reverse MCP 连接一个真实 Chrome，搞清楚平台前端**到底怎么请求收藏列表**、签名（如有）**到底怎么生成**：

1. **连接并导航**：`select_page` 确认目标标签页 → `navigate_page` 打开平台收藏页 URL（抖音是 `/user/self?showTab=favorite_collection`；需要新标签页用 `new_page`）。
2. **让用户登录**：触发登录弹窗后 `take_screenshot` 截图二维码给用户扫；`evaluate_script` 读 `document.cookie` 粗查登录 cookie 名（HttpOnly 的从下一步请求头里确认）。
3. **抓收藏列表请求**：`list_network_requests` 过滤（`resourceTypes: ["xhr","fetch"]` + `urlFilter` 传接口路径片段），找到真正的收藏列表接口后带 `reqid` 看详情，**逐项记录**：
   - **HTTP 方法**：抖音 `listcollection` 是 **POST**（用 GET 会 404 `Unsupported path(Janus)`，这个坑查了半小时）
   - **URL + query 公共参数**：完整复制（device_platform/aid/version_code 等一长串，保持与浏览器一致最稳）
   - **请求体**：抖音 POST body 只有 `count=10&cursor=0`（form-urlencoded）
   - **特殊 header**：如 `x-secsdk-csrf-token: DOWNGRADE`。注意内联展示的 cookie 头是 redacted 的，`outputFile` + `outputPart: "all"` 导出 JSON 才有完整值（含 HttpOnly，可直接喂第二步的 Python 原型）
   - **响应结构**：字段名、翻页 cursor 语义（快手 `pcursor` 末页返回 `"no_more"` 哨兵而非布尔 has_more）
4. **小心同名接口陷阱**：抖音同时存在 `mix/listcollection`（返回「收藏的**合集**」`mix_infos`）和 `aweme/listcollection`（收藏的**视频** `aweme_list`），别抓错。看清响应顶层字段再下结论。
5. **对照实验**（判断哪些参数/签名必需）：`evaluate_script`（任意脚本需 `confirm: true`）在页面里用 fetch 重放，分别试
   原样 / 篡改签名 / 去掉签名 / 去掉可疑 header，观察哪些是硬性要求。实测对照：抖音 a_bogus/msToken 都可省（拦截全靠 TLS 指纹层）；快手 `__NS_hxfalcon` 缺失/伪造一律 `result=50`（强校验），`kww` header 可省。
6. **签名逆向**（仅当对照实验证明签名强校验时）：
   - `search_in_sources` 搜签名参数名（如 `__NS_hxfalcon`）或生成函数名（如 `getSig4`），定位所在 bundle；
   - `save_script_source` 把整个（压缩）bundle 存到本地，用 acorn 按语法边界截取签名器 —— 快手的 `var Jose = (IIFE)` 自包含无依赖，整体剥离即可（截取别信括号计数，字符串字面量里的括号会坑你）；
   - 先在原页面 `evaluate_script`（`mainWorld: true` + `localFilePath` 传剥离后的文件）验证能产出有效签名，再移植到目标运行时（Node 需最小 window/document/navigator shim；快手 VM 还要求间接 eval + 事件循环内执行 + LF 换行，全记录在 `kuaishou/sig4.cjs` 文件头）。

### 第二步：Python 原型验证（`.venv` 里跑一次性脚本）

```python
from curl_cffi import requests
r = requests.post(url, data=f"count=10&cursor={cursor}",
                  headers={...含 cookie...}, impersonate="chrome", timeout=20)
```

验证三件事：

1. **认证方式**：cookies 从哪来。FavAPI 的账号体系用 playwright 持久化 profile，
   读 cookie 见 `douyin/api_client.py::profile_cookie_header`（起一次无头 Chromium 读 cookies 后关闭）。
2. **翻页语义**：抖音 cursor 是**服务端返回的时间戳 token**（上一页响应里的 `cursor` 字段作为下一页入参），不是偏移量。
   对外 `FetchResult.cursor` 仍保持与浏览器模式一致的「已抓条数偏移」语义，内部自行转换。
3. **节流**：翻页间隔别太快（抖音用 0.8s/页），防风控。

### 第三步：落地到 platform 代码

照 douyin 的结构：

| 文件 | 内容 |
|---|---|
| `constants.py` | 接口 URL、每页条数、翻页间隔 |
| `api_client.py` | `profile_cookie_header()`（profile → cookie 头）+ `fetch_xxx_page()`（单页，同步）+ `fetch_xxx()`（翻页循环，async，`asyncio.to_thread` 包同步请求） |
| `adapter.py` | `api_fetch_implemented = True`；`fetch_favorites` 开头两行分发；实现 `fetch_favorites_api`（解析 count/cursor → 调 api_client → 组装 FetchResult，on_batch 逐批回调） |
| `parser.py` | 复用/扩展响应解析（douyin 直接复用了浏览器模式的 `parse_listcollection`） |

前端只需一步：`web/src/data/mockFavData.ts` 该平台加 `apiFetch: true`。

### 第四步：验证清单

```bash
# 1. adapter 直测（含流式回调）
.venv/Scripts/python.exe -c "..."   # 参照 douyin：构造 AccountContext 调 fetch_favorites({'method':'api','count':N})

# 2. HTTP 链路（server 起在 8300）
curl -X POST http://127.0.0.1:8300/api/v1/fetch -H "Content-Type: application/json" \
  -d '{"platform":"<id>","account_id":"<acc>","action":"list_favorites","params":{"method":"api","count":10}}'

# 3. 校验兜底：不支持的平台应 400
curl ... -d '{"platform":"bilibili",...,"params":{"method":"api"}}'   # → 400 暂不支持

# 4. 回归：默认（不带 method）浏览器模式不受影响

# 5. 前端：账号详情 → 抓取表单出现「执行方式」select → 选 API 请求 → 抓取成功
```

## 4. 踩坑记录（全部实测过，别再踩）

0. **JS Reverse MCP 常见坑**：`evaluate_script` 默认跑在 isolated world，看不到页面 JS 全局变量，查页面上下文必须 `mainWorld: true`；
   内联展示的请求 cookie 头是 redacted 的，完整值只能 `outputFile` 导出；
   从 bundle 剥离 JS 代码时 Windows 下 Python `write_text` 默认把 `\n` 写成 `\r\n`，会悄悄破坏 VM 内部自解码字符串（必须 `newline="\n"`）；
   截取 IIFE 用括号计数必被字符串字面量里的括号坑，用 acorn 按语法边界截。
1. **GET/POST 搞错**：抖音 listcollection 必须 POST，GET 返回 `404 Unsupported path(Janus)`（网关层按方法路由）。
2. **空响应 = 指纹拦截**：HTTP 200 + `Content-Length: 0`。换 curl_cffi `impersonate="chrome"`，不要在 cookies 上浪费时间。
3. **uvicorn `--reload` 下 playwright 异步 API 起不来**：Windows 上 reload 模式的 event loop 是 SelectorEventLoop，
   不支持子进程，`async_playwright().start()` 抛 `NotImplementedError`。**解决**：读 cookies 用
   `asyncio.to_thread` + `sync_playwright`（同步 API 在线程内自建循环）。注意这也会导致浏览器模式在 dev 下失败——
   浏览器相关功能用 `server` 命令（无 reload）验证。
4. **平台覆写 `validate_params` 会绕过基类 method 校验**：所以统一校验放在 `task_executor.validate_fetch` 里强制执行。
5. **curl_cffi 是同步库**：async 上下文里必须 `await asyncio.to_thread(fn, ...)`，否则阻塞整个事件循环。
6. **登录态判定复用** `browser.has_login_cookies(cookies, LOGIN_COOKIE_KEYS)`，失效抛 `LoginExpiredError`，
   任务执行器会自动把账号标记 expired。
7. **procm 双实例**：dev 命令曾起过两个实例抢 8300 端口，排查前先 `procm list` 看重复。
   Windows 下 SO_REUSEADDR 允许双进程同时 LISTEN，请求会随机打到坏实例（症状：秒回 503 且日志无请求记录），
   `netstat -ano | grep 8300` 看 LISTEN 的 PID 是否唯一，`taskkill /PID <旧reloader> /T /F` 清理。
8. **`--reload` 下 playwright 失效的两个触发链**（Windows）：
   a) `--loop asyncio:ProactorEventLoop` 只对初始 worker 生效，WatchFiles 重载出的新 worker 退回
      SelectorEventLoop → playwright 子进程 `NotImplementedError`（秒回 503）；
   b) 默认监听整个仓库，**运行时写库（如身份回填 update_account）就会触发重载**——用户没改代码也会踩 a)。
   修复（procm-commands.json 的 dev 已带）：`--reload-dir app` 只监听后端代码；
   症状排查：503 秒回 + worker 日志无请求记录时，`netstat -ano | grep 8300` 看 LISTEN 是否唯一、
   `wmic` 查 python 命令行是否带 `--loop`（不带的实例是手动起的坏实例，taskkill 清理后按 procm-command 重启）。

## 5. 平台支持现状

| 平台 | 浏览器模拟 | API 请求 | 备注 |
|---|---|---|---|
| douyin | ✅ | ✅ | 首个落地，代码即模板 |
| bilibili | ✅ | ✅ | 2026-09 接入：收藏夹接口无 WBI；视频详情 `view` 无签名、播放直链 `playurl` 需 WBI 签名（mixin key 取自 nav 的 wbi_img，纯 Python md5）；mp4 单文件走 `platform=html5` 端点（匿名 720P 封顶），1080P+/4K 走 DASH 双流 + ffmpeg 合并；坑见 `bilibili/api_client.py` 模块注释（跨域 referer 必须只发根 origin，带视频页完整 referer 一律 412） |
| xiaohongshu | ✅ | ✅ | 2026-09 接入：x-s/x-s-common/x-t 签名用 [xhshow](https://github.com/Cloxl/xhshow) 纯算生成（XYS_ 格式）+ curl_cffi 直连；坑见 `xiaohongshu/api_client.py` 模块 docstring（query 编码必须与签名逐字节一致、cookies 传 dict） |
| wechat | JSON 导入 | — | 无浏览器抓取概念，不适用 |
| youtube | ✅ | ❌ | 按需接入 |
| kuaishou | ✅ | ✅ | 2026-09 接入：`__NS_hxfalcon` 签名强校验（缺失/伪造 → result=50），签名 VM 从站点 bundle 剥离到 `kuaishou/sig_vm.js`，经 `sig4.cjs`（Node CLI ≥16，系统依赖）离线生成；坑见 `kuaishou/api_client.py` 模块 docstring（profile 混入 live/id 域 cookie 必须按 domain 过滤，否则多个 userId 并存 → result=109；VM 必须间接 eval + 事件循环内执行；换行符必须 LF） |
| threads | ✅ | ✅ | 2026-09 接入：GraphQL（`/graphql/query`），直连需 `x-csrftoken` + lsd + 完整 relay pv 标志（`constants.SAVED_PV_FLAGS`）；代理沿用声明式 auto 解析 |
| instagram | — | ✅ | 2026-09 接入（仅 API 直连）：REST v1（收藏 `feed/saved/posts`、关注 `friendships/{uid}/following`、详情 `media/{pk}/info`，最小头集 x-csrftoken + x-ig-app-id）+ GraphQL 投稿查询（form 最小集 lsd/variables/doc_id，av/fb_dtsg 可省；variables 按 username 定位 + 3 个 Polaris pv 标志）；lsd 从首页 HTML 提取；需代理出网；CDN（scontent-*.cdninstagram.com）直链仅 UA；博主主键 = username（投稿 GraphQL 不认数字 pk）；坑详见 `instagram/api_client.py` 模块 docstring |
| tiktok | ✅ | ✅ | 2026-09 接入（外部扩展模式同快手）：签名（X-Gnarly/X-Bogus/msToken/X-Dynosaur/verifyFp）**全部不做强校验**，但 query 需保留 msToken+X-Bogus=1 占位（全删触发空响应软拦截）；收藏 `user/collect/item_list` 强登录态（复制出的 cookie 数分钟即被拒，必须 profile 活会话，status_code=8 → LoginExpiredError）；点赞 `favorite/item_list` 半公开（私密点赞返回空列表非报错）；用户信息走个人主页 HTML 的 `__UNIVERSAL_DATA_FOR_REHYDRATION__` SSR 解析（`/api/user/detail/` 对非浏览器上下文返回空 userInfo）；secUid 不落 cookie，登录后 refresh_profile 从浏览器提取回填 extra；坑详见 `tiktok/api_client.py` 模块 docstring |

## 6. 快速回顧：一次成功接入的样子

```
JS Reverse MCP 连浏览器 → 用户扫码登录 → 抓包记录接口细节 → 对照实验判定签名是否必需
    ↓（签名强校验时）
search_in_sources / save_script_source 定位并剥离签名器 → 页面验证 → Node 离线生成
    ↓
Python 一次性脚本：profile cookies + curl_cffi(impersonate="chrome") 原型打通
    ↓
constants.py / api_client.py / adapter.py 三件套 + mockFavData.ts 加 apiFetch
    ↓
四项验证（直测 / HTTP / 400 兜底 / 回归浏览器模式）→ 前端实测
```

抖音全流程参考提交：`app/platforms/douyin/api_client.py`（新增）、`adapter.py`（分发 + fetch_favorites_api）、
`base.py` / `task_executor.py` / `registry.py`（通用层）、前端 4 文件（types / api / mockFavData / AccountDetail）。

快手全流程参考（含签名逆向）：`app/platforms/kuaishou/`（`sig_vm.js` 剥离的签名 VM +
`sig4.cjs` Node CLI + constants / parser / api_client / adapter）、`registry.py`（声明式注册后覆盖）、
前端 `web/src/data/platforms.ts` 加条目；声明式浏览器模式通过继承 `DeclarativeAdapter` 保留，零重复实现。

## 7. 平台 API 操作（写操作 / 管理类）

与收藏抓取（fetch/task 体系）平行的另一条通道：`ApiOperation` 声明 → 前端「平台 API 操作」卡片
（账号详情页，按 `/api/v1/platforms` 下发的元数据动态渲染）→ 点击弹表单 → `execute_api_operation` 执行。

### 7.1 后端三件套

1. `base.py`：`ApiOperation` / `ApiOperationParam`（表单 schema：key/label/type/required/placeholder/help，
   type 支持 text | textarea | number | date；`danger=True` 前端弹二次确认）+ adapter 的
   `api_operations` 声明与 `execute_api_operation(op_id, account, params)` 分发。
2. 路由：`POST /api/v1/accounts/{account_id}/operations/{op_id}`（body `{"params": {...}}`），
   同步执行返回结果 JSON；参数问题 400 / 登录失效 409 并标记 expired / 其余 502。
3. registry `_info` 自动把 `api_operations` 元数据下发给前端，**前端零改动**即可出新卡片。

### 7.2 抖音已实现的操作

| op_id | 说明 | 参数 |
|---|---|---|
| `list_favorites` | 只读拉取收藏列表（可选日期过滤，不入库） | count / date_from / date_to |
| `cancel_collect_multi` | 批量取消收藏，**ID 列表与日期区间二选一**（日期优先） | aweme_ids / date_from / date_to |

Threads 已实现：`save_post`（收藏帖子，media_id）/ `cancel_saved_multi`（批量取消，post_ids）。
写 mutation 与读接口同套最小字段集直连（无需 fb_dtsg），文档见 `threads/constants.py`。

快手已实现 11 个操作（`kuaishou/adapter.py`）：

| op_id | 说明 | 参数 |
|---|---|---|
| `get_profile` | 获取当前登录用户信息 | — |
| `list_favorites` / `list_likes` | 只读拉取收藏/点赞列表 | count |
| `like_item` / `cancel_like_item` | 单视频点赞/取消 | photo_id（必填）、user_id（作者，可选） |
| `collect_item` / `cancel_collect_item` | 单视频收藏/取消 | 同上 |
| `like_multi` | 批量点赞，当日次数用完（liked_remain_count=0）自动停止 | photo_ids |
| `cancel_like_multi` / `cancel_collect_multi` | 批量取消点赞/收藏 | photo_ids / 日期区间二选一 |
| `resolve_download_urls` | 按视频 ID 解析下载直链（平台下载 → aria2c） | photo_id（必填） |

快手视频详情走 `POST /graphql`（`visionVideoDetail`），**不在 `__NS_hxfalcon` 签名白名单**
（直连即可）；CDN 直链（photoUrl / manifest representation / H.265 系）仅 UA 即可下载。

快手写接口要点：`photo/collect`、`photo/like` **不在 `__NS_hxfalcon` 签名白名单**
（直连即可，比读接口还简单）；`photo/like` 强校验作者 `user_id`（缺失 → result=21，
批量 ID 模式从 contents 表自动补全，未入库视频先抓取入库）；
`photo/collect` 的作者 `userId` 可省；`exp_tag` 均可省。批量操作逐条执行 + 0.5s 节流。

Bilibili 已实现 `cancel_favorites`（批量取消收藏）与 `resolve_download_urls`
（按 BV 号解析下载直链，支持粘贴完整链接、多 P 指定分 P，默认 P1）。
下载要点：mp4 单文件走 `platform=html5 + fnval=1`（音视频合一，匿名 720P 封顶，
登录态失效自动回退匿名）；高画质（1080P+/4K，需登录态）走 `fnval=16` 的 DASH
双流（link 附 `audio_url`，kind="dash"）—— download_worker 双 aria2 任务下载
`.video.m4s` / `.audio.m4s` 后 `ffmpeg -c copy` 合并为单个 mp4 并清理分片；
未安装 ffmpeg 时自动回落 mp4 单文件。CDN 直链实测仅 UA 即可下载。

日期区间过滤复用 `app/utils.py::parse_date_window / filter_by_date_window`
（collected_at 缺失由 parser 兜底发布时间）；task_executor 的抓取过滤也走同一份实现。

TikTok 已实现 `resolve_download_urls`（按帖子 ID/链接解析直链，视频+图文）。
要点（坑详见 `tiktok/api_client.py` 模块 docstring）：详情 XHR `/api/item/detail`
有签名强校验（X-Gnarly 与完整 query 绑定，改任一参数即空响应），不可直连；
改走帖子页 HTML 的 SSR 段 `webapp.video-detail`（公开访客可见），图文帖必须
用 `/video/{id}` 路径访问才有该段（`/photo/` 路径不渲染），URL 中 handle 不参与
定位（占位即可）。视频 CDN 直链下载需页面会话 cookie（tt_chain_token，仅 UA 或
仅 ttwid 均 403），且 `v16-webapp-prime` 主机对部分出口 IP 拒绝、`v19` 可用
（parser 同档 UrlList 内优先 v19）；图片直链仅 UA 即可。

### 7.3 性能要点：提前终止

收藏列表按时间倒序，翻页时传 `stop_before=dt_from`：某页全部条目可解析时间且最旧一条已早于下界
即停止翻页（后续更旧不可能命中）。抖音 2300+ 条收藏，近期区间从 5 分钟降到 ~1 秒；
`date_from` 早于全部收藏时仍会翻完（正确行为，匹配需要全量）。

### 7.4 新平台接入

同第 3 节流程抓包拿到接口 → `api_client.py` 写请求函数（curl_cffi）→ adapter 声明 `ApiOperation`
并在 `execute_api_operation` 按 op_id 分发 → 前端自动出卡片。危险操作记得 `danger=True`。

## 8. 特别关注（follows）体系：2026-09 接入

与抓取/操作平行的第三条通道：`GET|POST|PATCH|DELETE /api/v1/follows/**`（`app/api/follows.py`），
前端「特别关注」路由（Sidebar follows → FollowsView / 博主主页 / 播放器）。

涉及接口（全部 GET 读接口，curl_cffi 直连，无需 guard 头/签名，实测 2026-09）：

| 接口 | 用途 | 分页 |
|---|---|---|
| `/aweme/v1/web/user/following/list/` | 当前账号关注列表（仅需 sec_user_id，user_id 可空） | offset 偏移 |
| `/aweme/v1/web/aweme/post/` | 博主主页发布作品（与 favorite 同构，自带 play_addr/images） | max_cursor 游标 |
| `/aweme/v1/web/aweme/detail/` | 作品播放信息（视频直链/图文原图，`parse_play_info`） | — |

数据模型：`follow_authors`（博主主键 sec_uid，uid 为未读数关联键——**作品 author.uid 与关注列表
返回的 uid 一致**，同步时会自动回填防漂移）+ `follow_reads`（作品已读标记）；
作品入库走标准 `save_fetch_result(account, items, source="特别关注")`，数据页可查。

媒体播放：抖音 CDN 拒绝浏览器直连（referer/UA），前端 `<video>/<img>` 统一走
`GET /follows/media?url=...` 流式代理（域白名单 + Range 透传，同步 def 路由自动入线程池）。

