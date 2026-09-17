# web 索引变更记录

## 2026-09-17 22:36 — 首次生成

- 随根目录第二次 `/init-project` 运行创建：`web/CLAUDE.md` 索引 + `claude/` 10 个详情文件（无对外接口，省略 public-interfaces.md）。
- 扫描方式：独立探索代理全量扫描 web/（构建配置、App 骨架、api.ts 12 分组 + 3 SSE、约 40 个组件、类型与数据模块）。
- 覆盖率：全部 tsx/ts 源文件经结构化阅读；DataBrowserView.tsx（≈1990 行）与 App.tsx（≈830 行）仅结构性阅读，未逐行审。
- 待深挖建议：拆分 DataBrowserView 时先补此处细节。
