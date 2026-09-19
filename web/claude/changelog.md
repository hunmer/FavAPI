# web 索引变更记录

## 2026-09-19 13:44 — 增量更新（第二次运行）

- 主要变化：DataBrowserView 1990→904 行，拆出 BrowserFilterPanel/BrowserContent/BrowserToolbar/DataItemCard/AiTaggingModal+useAiTagging/BrowserTagModals/BrowserDeleteModals；新增 Follows 组件族 7 文件（第 8 个页面视图：博主列表/作者主页三视图/播放弹窗/一键同步 SSE）；新增 AlertDialog（替代原生 alert/confirm，未提交）、ViewModeSwitch 共用化；api.ts 910→1255 行（+follows 14 函数 +syncStream SSE）；platforms.ts 11→12（instagram）；Header 移除新建账号按钮、actions 槽按 tab 注入。
- 扫描方式：探索代理补扫 Follows/Data 全部文件与未提交 diff，主对话核对后写入 overview/module-responsibilities/file-map/data-model/conventions/CLAUDE.md。
- 覆盖率：63 个 ts/tsx 中变化文件全读；SettingsView（1025 行）与 Accounts/AccountDetail/（13 文件）未逐行审。

## 2026-09-17 22:36 — 首次生成

- 随根目录第二次 `/init-project` 运行创建：`web/CLAUDE.md` 索引 + `claude/` 10 个详情文件（无对外接口，省略 public-interfaces.md）。
- 扫描方式：独立探索代理全量扫描 web/（构建配置、App 骨架、api.ts 12 分组 + 3 SSE、约 40 个组件、类型与数据模块）。
- 覆盖率：全部 tsx/ts 源文件经结构化阅读；DataBrowserView.tsx（≈1990 行）与 App.tsx（≈830 行）仅结构性阅读，未逐行审。
- 待深挖建议：拆分 DataBrowserView 时先补此处细节。
