# web 架构总览

## 定位

FavAPI 的 Web 管理控制台（`favapi-web-console`）：React 19 + Vite 6 + TypeScript 5.8 + Tailwind 4 单页应用，覆盖仪表盘、账号管理（扫码登录/同步流式抓取/平台写操作）、收藏数据浏览与 AI 打标、特别关注（博主/作者主页/播放）、任务监控、定时调度、下载队列、系统设置。所有数据来自后端 `/api/v1`（dev 经 Vite 代理，生产由 FastAPI 托管 `web/dist`）。

## 骨架

- `main.tsx`：StrictMode + **HashRouter** + `<App />`（后端 StaticFiles 无 SPA 回退路由，hash 路由免后端配合）。
- `App.tsx`（约 885 行）：唯一的编排层——8 个页面视图切换（react-router 路径首段驱动，未知回落 dashboard；`/follows/author/:secUid` 子路由由 FollowsView 内部派发）、账号详情经 `?account=<id>` 查询参数双向同步（支持浏览器后退）、全部应用状态 useState/useCallback（**无状态管理库**）、初始数据加载与轮询（异步抓取 3s、下载 badge 15s）、Toast、全局 Modal、根挂 `<AlertDialogHost />`（命令式 confirm/alert）。
- 布局：左侧深色 `Sidebar` + `Header`（全局搜索/抓取进度 + 按 tab 注入的 actions 槽：follows 显示一键更新按钮、data 显示新建下载）+ main 区 motion 动画切换视图。

## 8 个页面视图

dashboard / accounts（列表↔详情二态）/ data / follows（列表↔作者主页二态）/ tasks / schedule / downloads / settings。

## 数据流

`api.ts` 统一封装（BASE=/api/v1，snake_case 行类型 → UI 类型映射），组件不直接 fetch。4 个 SSE 流式接口手写 reader 解析：fetchStream（抓取）、executeOperationStream（平台操作）、tagStream（AI 打标）、syncFollowPostsStream（特别关注一键同步）。

## 设计取舍

| 取舍 | 理由 |
|------|------|
| HashRouter 而非 BrowserRouter | 后端 StaticFiles 托管无回退路由 |
| 无状态管理库 | 单页数据量小，App 级 useState 足够；代价是 App.tsx 偏大 |
| 平台元数据静态 + 运行时合并 | `data/platforms.ts` 静态 12 平台（图标/配色/followsApi），启动时按 GET /platforms 更新 isSupported 并动态追加未知平台 |
| Tailwind 4 + class 式暗色 | `@custom-variant dark`；动效系统 CSS 变量 + prefers-reduced-motion 降级 |
| 命令式 AlertDialog（useSyncExternalStore） | 全局确认弹窗免层层传 props，替代原生 alert/confirm |
| DevInspector 仅 dev | vite 插件注入 JSX 行号 data 属性，点击可在编辑器打开源码（REACT_EDITOR） |

## 运行形态

- dev：`npm run dev` → 127.0.0.1:3000（host 0.0.0.0），`/api` 代理 `FAVAPI_BACKEND`（默认 http://127.0.0.1:8300）。
- 生产：`npm run build` → `dist/`，由后端 `app/web/router.py` 托管于 8300 根路径；无需 Node 运行时。
