# web — FavAPI 管理控制台（React SPA）

FavAPI 的前端单页应用：React 19 + Vite 6 + TypeScript 5.8 + Tailwind 4，无状态管理库。覆盖仪表盘、账号管理（扫码登录/平台写操作）、收藏数据浏览与 AI 打标、**特别关注**（博主列表/作者主页三视图/播放弹窗/一键同步）、任务监控、定时调度、下载队列、系统设置 8 个页面视图。所有数据来自后端 `/api/v1`：dev 在 3000 端口经 Vite 代理，生产构建产物 `dist/` 由 FastAPI 直接托管。

## 约定的规则

- 命令：`npm run dev`（3000，代理 FAVAPI_BACKEND=8300）/ `npm run build`（产物给后端托管）/ `npm run lint`（tsc --noEmit，唯一检查）。
- 改前端后要出现在 8300 页面必须重新 build，刷新浏览器无效。
- snake_case → camelCase 转换只写在 `api.ts` 的 `to*` 映射，组件只消费 `types.ts` 的 UI 类型。
- 平台操作表单/按钮由后端 `GET /platforms` 动态渲染，前端不硬编码平台能力。
- 全局 Alert/Confirm 用 `AlertDialog.tsx`（`await confirmDialog/alertDialog`），不用原生 `alert`/`window.confirm`。
- 浮层点击外部关闭统一 `hooks/useDismiss.ts`；视图切换（grid/waterfall/list）统一 `ViewModeSwitch`。
- 用 HashRouter（后端无 SPA 回退路由），勿改 BrowserRouter。
- 无测试/ESLint；至少跑 `npm run lint`。双锁文件并存，别混用包管理器。

## 文件索引

| 文件 | 用途 | 何时阅读 |
|------|------|----------|
| [架构总览](claude/overview.md) | 骨架、数据流、设计取舍 | 理解整体结构时 |
| [开发约定](claude/conventions.md) | 命令、环境变量、风格、禁止事项 | 动手改代码前 |
| [模块职责](claude/module-responsibilities.md) | 各组件/模块职责全表 | 定位改动位置时 |
| [入口与构建](claude/entrypoints.md) | main.tsx、Vite 配置、构建托管链 | 启动/构建问题时 |
| [依赖与配置](claude/dependencies-and-config.md) | package.json、锁文件、环境变量 | 升级依赖/改配置时 |
| [数据模型](claude/data-model.md) | UI 类型、后端映射、App 状态、平台元数据 | 涉及数据流/类型时 |
| [测试与质量](claude/testing-and-quality.md) | lint、人工验证路径、技术债清单 | 评估风险时 |
| [文件地图](claude/file-map.md) | 目录树与修改热点 | 找文件时 |
| [FAQ](claude/faq.md) | 常见问题与定位 | 遇到异常行为时 |
| [changelog](claude/changelog.md) | 本索引生成记录 | 重跑 /init-project 时 |

（本模块为纯前端消费方，不对外暴露接口，无 public-interfaces.md）

## 扫描状态

- 更新时间：2026-09-19 13:44（第二次运行，增量更新）。
- 已扫描：全部 63 个 ts/tsx 源文件（两个探索代理累计）；本次重点补扫 Follows 7 组件族、Data 12 组件拆分、未提交 diff（AlertDialog/Header/App/FollowsView）。
- 跳过：`node_modules/`、`dist/`、锁文件内容。
- 下一步建议：`Settings/SettingsView.tsx`（≈1025 行，全仓第一大）与 `App.tsx`（≈885 行）仍仅结构性阅读，拆分前建议深挖；Accounts/AccountDetail/ 13 文件未逐行审。
