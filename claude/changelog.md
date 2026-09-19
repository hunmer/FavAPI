# 索引变更记录（/init-project 生成记录，非产品 Changelog）

## 2026-09-19 13:44 — 增量更新（第三次运行）

- 触发：09-17 后项目新增「特别关注」follows 体系、Instagram 平台、桌面化发布链路。
- 主要变化：平台 8→9（instagram 纯 API 直连、需代理）；表 8→10（follow_authors/follow_reads）；api 9→12 路由文件（follows 14 路由含 SSE 媒体代理、covers、notifications）；services 13→18（follow_store/cover_worker/notification_store/raw_store/aria2_service/updater）；下载器 +aria2c；favorites 增 source 来源维度、删除联动清孤儿；main.py 单实例锁 + pywebview 窗口 + tufup 自动更新 + GitHub Actions 便携包发布；前端 DataBrowserView 1990→904 行拆出 8 个子组件、新增 Follows 7 组件族（第 8 个页面视图）、AlertDialog 全局弹窗。
- 扫描方式：两个并行探索代理分别补扫后端变化区（instagram/follows/browser/server/handoff）与前端变化区（Follows/Data 拆分/未提交 diff），主对话核对 requirements/main.py/release.yml 后写入。
- 覆盖率：app/ 87 个 py 中变化文件全读，未变文件沿用上次结论；web/src 63 个 ts/tsx 变化文件全读。
- 待深挖：`handoff/_headless_probe.py`（TikTok headless UA 探测）进行中未落码；`SettingsView.tsx`（1025 行）与 `App.tsx`（885 行）仍仅结构性阅读。

## 2026-09-17 22:36 — 全量增量更新（第二次运行）

- 触发：自首扫后项目规模翻数倍，重写根 `CLAUDE.md` + `claude/` 全部 11 个详情文件。
- 主要变化：平台 2→8（bilibili/xiaohongshu/kuaishou/tiktok/threads/youtube/wechat 落地，声明式平台体系上线）；表 4→8（ai_agents/tag_groups/schedules/downloads）；服务层 4→13（调度/下载/AI 打标/设置等）；API 3→9 个路由文件并新增 SSE 流式接口；Web 界面由 Jinja2+原生 JS 换成 React 19 + Vite 6 SPA（web/ 新增独立 CLAUDE.md 索引 + 10 个详情文件）。
- 扫描方式：两个并行探索代理分别全量扫描后端 app/（入口/API/services/platforms/database/config/tests）与前端 web/（构建/骨架/api.ts/组件/类型），主对话核对现有文档与 procm-commands.json 后写入。
- 覆盖率：后端 Python 源 78 文件与 web/src 约 50 文件全部经代理抽样/全读；HTML 模板已随 Jinja2 界面移除。
- 待深挖：`app/platforms/*/api_client.py` 签名细节未逐行审（已由各平台 adapter 层描述覆盖）；`web/src/components/Data/DataBrowserView.tsx`（1991 行）仅结构性阅读。

## 2026-09-10 18:26 — 初始生成

- 首次运行 `/init-project`，创建根 `CLAUDE.md` 索引 + `claude/` 全部 11 个详情文件。
- 扫描范围：24 个 Python 源文件全部读取（100%）；5 个 HTML 模板仅确认职责未逐行读。
- 项目为单一 `app/` 包，未识别出需要独立 CLAUDE.md 的子模块。
