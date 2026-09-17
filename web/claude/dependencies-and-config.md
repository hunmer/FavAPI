# web 依赖与配置

## dependencies（package.json）

| 包 | 用途 |
|----|------|
| react / react-dom ^19.0.1 | UI 框架 |
| react-router-dom ^7.18.3 | HashRouter + 路由 hooks |
| vite ^6.2.3 / @vitejs/plugin-react ^5.0.4 | 构建 |
| tailwindcss ^4.1.14 + @tailwindcss/vite | 样式（CSS-first，无 tailwind.config） |
| motion ^12.23.24 | 视图切换/组件动画 |
| lucide-react ^0.546.0 | 图标 |
| @react-dev-inspector/vite-plugin + react-dev-inspector ^2.0.1 | 元素定位到源码（dev） |
| @babel/core + @types/babel__core | inspectorTransform 注入 JSX 行号用 |

## devDependencies

@types/node ^22、autoprefixer ^10.4、esbuild ^0.25、tailwindcss ^4.1.14、typescript ~5.8.2。

**无**：状态管理库、测试框架、ESLint、postcss.config（Tailwind 4 经 Vite 插件接入）。

## 锁文件

`package-lock.json` 与 `pnpm-lock.yaml` 并存——历史原因，装依赖时二选一保持一致。

## 配置文件

| 文件 | 要点 |
|------|------|
| `vite.config.ts` | FAVAPI_BACKEND 代理、port 3000 host 0.0.0.0、inspector 双插件、别名 `@` |
| `tsconfig.json` | ES2022 / bundler / noEmit / strict `@/*` |
| `.gitignore` | node_modules / dist |

## 环境变量

- `FAVAPI_BACKEND`：dev 代理目标（默认 http://127.0.0.1:8300）。
- `REACT_EDITOR`：DevInspector 打开源码的编辑器命令（默认 `code`）。
- 无 .env 文件。

## 静态资源

`public/site_icons/`：bilibili/douyin/kuaishou/tiktok/weibo（.ico）+ xiaohongshu（.ico）+ wechat（.svg），共 7 个；与 SiteIcon.tsx 静态映射一致。threads/youtube/zhihu/twitter 无本地图标，走后端 `/platforms/{name}/icon`。
