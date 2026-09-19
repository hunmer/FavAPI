# web 开发约定

## 命令（package.json scripts；procm 里也有 `web` 命令）

```bash
npm run dev       # Vite dev，127.0.0.1:3000，/api 代理到 FAVAPI_BACKEND（默认 8300）
npm run build     # 生产构建 → dist/（后端 FastAPI 托管）
npm run lint      # tsc --noEmit（唯一的类型/质量检查）
npm run preview   # 本地预览构建产物
npm run clean     # rm -rf dist
```

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `FAVAPI_BACKEND` | http://127.0.0.1:8300 | dev 代理目标（vite.config.ts） |
| `REACT_EDITOR` | `code` | DevInspector 点击元素打开源码的编辑器命令 |

无 .env 文件；路径别名 `@` → web 根目录。

## 代码风格

- 组件按功能域分目录（Accounts/Dashboard/Data/Follows/Tasks/Schedule/Downloads/Settings），账号详情子组件在 `Accounts/AccountDetail/`。
- 后端 snake_case → UI camelCase 的转换只发生在 `api.ts` 的 `to*` 映射函数；组件只消费 UI 类型（types.ts）。
- 全局确认/提示一律用 `AlertDialog.tsx` 的 `await confirmDialog()/alertDialog()`，禁止原生 `alert`/`window.confirm`（Host 已挂 App 根部）。
- 样式：Tailwind 4 工具类为主；动效用 `motion`（lucide-react 图标）；入场动效 class（card-enter 等）见 index.css，尊重 prefers-reduced-motion。
- 弹出菜单/浮层的点击外部关闭统一用 `hooks/useDismiss.ts`（window 捕获阶段监听），不要各写各的。
- 下拉选择用 `DropdownSelect`，不用原生 select；视图切换（grid/waterfall/list）用 `ViewModeSwitch` + `readViewMode(storageKey)`。
- localStorage 持久化偏好：theme、fullPage、视图模式、过滤条件、平台操作表单值（键名见各组件）。

## 禁止 / 注意事项

- 后端接口在 `/api/v1`，不要写死完整域名（dev 走代理）。
- 平台图标：优先 `public/site_icons/` 静态映射（SiteIcon.tsx），新平台先放图标文件；未收录自动回退后端 icon_url。
- 无测试框架、无 ESLint；改动后至少跑 `npm run lint`。
- 双锁文件并存（package-lock.json + pnpm-lock.yaml），装依赖时保持与现有锁一致，不要混用产生第三种状态。
- App.tsx 内 `[DBG-ACC]` console.warn 是调试残留，清理前先确认问题已解。
