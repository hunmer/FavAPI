# web 测试与质量

## 检查命令

```bash
npm run lint    # tsc --noEmit —— 唯一自动化检查
npm run build   # 构建能否通过（间接验证类型与导入）
```

无单元测试框架、无 E2E、无 ESLint/Prettier、无 CI。

## 人工验证路径

dev（127.0.0.1:3000 代理后端）或 build 后走 8300：登录 → 抓取 → 数据页过滤/多选/AI 打标 → 定时/下载/设置各页走一遍；移动端视口看 Sidebar 折叠。

## 已知质量风险 / 技术债

- `Data/DataBrowserView.tsx` 约 1990 行：过滤、多选、批量操作、AI 打标入口全在一个组件，改动成本高，是最该拆分的文件。
- `App.tsx` 约 830 行集中全部全局状态（无状态库的代价）。
- `data/mockFavData.ts` 大量遗留 mock 常量未清理（仅 PLATFORMS re-export 在用）。
- App.tsx 有 4 处 `[DBG-ACC]` console.warn 调试残留（openAccountDetail/closeAccountDetail/URL-sync/reloadAccounts）。
- 双锁文件并存（package-lock.json + pnpm-lock.yaml），存在重复安装产生分歧的隐患。
- `types.ts` 的 `PrimaryTab` 疑似无引用。
- 依赖较新（React 19 / Vite 6 / Tailwind 4 / router 7），升级时注意 Tailwind 4 无 tailwind.config 的 CSS-first 写法与 `@custom-variant dark` 语法。
