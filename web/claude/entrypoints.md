# web 入口与构建

## 入口

- `index.html` — Vite 入口 HTML。
- `src/main.tsx` — StrictMode + HashRouter + App 挂载。
- `src/App.tsx` — 视图编排、路由同步、数据加载与轮询、全局 Modal/Toast。

## 启动流程（dev）

`npm run dev` → Vite 读 `vite.config.ts`：
1. `BACKEND = FAVAPI_BACKEND || http://127.0.0.1:8300`，注册 `/api` 代理（changeOrigin）。
2. dev server 监听 `0.0.0.0:3000`。
3. 插件：`@vitejs/plugin-react`、`@tailwindcss/vite`、自定义 `inspectorTransform()`（Babel 给 JSX 节点注入 data-inspector-line/column/relative-path，仅 dev 生效）、`inspectorServer()`（`/__open-stack-frame-in-editor` 路由，按 REACT_EDITOR 打开编辑器）。
4. 别名 `@` → web 根。

后端不启动时页面能开但所有请求代理失败（Network Error）。

## 构建流程（生产）

`npm run build` → Vite 产物输出 `dist/`（默认 outDir）→ 后端 `app/web/router.py` 检测 `web/dist/index.html` 存在即挂 StaticFiles(html=True) 托管于 8300 根路径。前端无 SSR、无 Node 运行时依赖。

改动前端后要让它出现在 8300 页面上必须重新 build；只刷新浏览器不够。

## TS 配置（tsconfig.json）

target ES2022 / module ESNext / moduleResolution bundler / jsx react-jsx / noEmit / strict 路径 `@/*`。`npm run lint` 即 `tsc --noEmit`。
