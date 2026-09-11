# FavAPI Web Console

FavAPI 的 Web 管理界面（React 19 + Vite + Tailwind 4），覆盖账号管理、扫码登录、手动抓取（同步流式 / 异步）、任务监控、收藏数据浏览与定时同步调度。所有数据来自后端 `/api/v1` 接口。

## 开发模式

```bash
npm install
npm run dev   # http://localhost:3000，/api 自动代理到 127.0.0.1:8300（FAVAPI_BACKEND 可覆盖）
```

## 生产构建

```bash
npm run build   # 产物输出到 web/dist
```

构建后由 FastAPI 直接托管（`app/web/router.py`），访问 `http://127.0.0.1:8300/` 即可，无需 Node 进程。

## 结构

- `src/api.ts` — 后端接口封装 + UI 类型映射（snake_case → console 类型）
- `src/App.tsx` — 数据流编排（加载 / 5s 轮询 / 各类操作回调）
- `src/components/` — 视图组件（Dashboard / Accounts / Data / Tasks / Schedule / Settings）
- `src/data/mockFavData.ts` — 仅保留 `PLATFORMS` 平台元数据（isSupported 在运行时按后端实现情况更新）
