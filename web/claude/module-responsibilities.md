# web 模块职责

## 顶层与通用组件（components/）

| 文件 | 职责 |
|------|------|
| `Sidebar.tsx` | 7 tab 竖直导航（motion 指示器）、下载 badge、主题切换、头像 |
| `Header.tsx` | 全局搜索、新建账号、RunningFetchInfo 抓取进度指示 |
| `DropdownSelect.tsx` | 统一风格下拉选择器（支持计数后缀） |
| `SiteIcon.tsx` | 平台图标：静态映射 + 后端 icon_url 兜底（模块级缓存） |
| `DevInspector.tsx` | dev 专用元素定位器（生产不渲染） |

## 功能域组件

| 目录 | 组件与职责 |
|------|-----------|
| `Dashboard/` | DashboardView 总布局；StatCard 数字滚动；ActiveAccountCard 活跃账号一键同步；CalendarCard 收藏日历热力（被 ScheduleView 复用，点击带日期过滤跳数据页）；RecentCollectionCard；ScheduleQueueCard |
| `Accounts/` | AccountsList 卡片网格与批量刷新身份；CreateAccountModal；QRCodeLoginModal 扫码登录状态机（startLogin→轮询 loginStatus）；CookiesModal 查看 cookie |
| `Accounts/AccountDetail/` | index 组合页；Header 操作工具栏；InfoCards 登录/身份/收藏夹统计；PlatformOperations 平台 API 操作表单（SSE 流式，表单值 localStorage 持久化）；FolderPicker B 站收藏夹管理（编辑/删除/批量删，请求间隔防风控）；ScrapeForm 抓取表单（平台专属参数）；ScrapeStream 实时反馈流；TasksTab 最近任务；ClearFavoritesModal / DeleteAccountModal 确认弹窗 |
| `Data/` | **DataBrowserView（约 1990 行，最大组件）**：过滤面板（账号/平台/收藏夹/作者/日期/标签/关键词）、网格/列表切换、多选批量操作、AI 打标入口；DataItemCard 封面卡片（右键菜单/隔离浏览器打开/入下载队列）；DownloadConfirmModal 选下载器；ItemActionMenu；ItemDetailModal 详情与手动编辑标签 |
| `Tasks/TasksView.tsx` | 任务列表：状态筛选、手动刷新、清空记录 |
| `Schedule/ScheduleView.tsx` | 计划列表（触发/启停/删除）、创建计划（cron、list_favorites/ai_tag）、AI Agent 配置管理；复用 CalendarCard |
| `Downloads/DownloadsView.tsx` | 下载队列：3s 自轮询进度、重试/暂停/删除/文件管理器定位（自取数据） |
| `Settings/SettingsView.tsx` | 运行参数（profile/headless/间隔/超时/下载目录/并发）、主题与布局切换、头像上传、AI Agent CRUD+连通性测试 |

## 非组件模块（src/）

| 文件 | 职责 |
|------|------|
| `api.ts`（约 910 行） | 全部后端接口封装：12 分组（平台/账号/身份刷新/任务数据/统计/抓取/定时/AI/标签/收藏删除/下载/设置）+ 3 个 SSE 流（fetchStream/executeOperationStream/tagStream）+ formToParams 表单→平台 params 抹平 |
| `types.ts` | UI 类型：NavTab(7)、Account/AccountStatus、BilibiliFolder、TaskRecord、ScrapedItem、ScrapingFormData、ScheduledSync 等 |
| `data/platforms.ts` | 平台静态元数据 PLATFORMS（11 个：含未实现的 zhihu/weibo/twitter）+ 运行时 isSupported 合并 |
| `data/mockFavData.ts` | re-export PLATFORMS + 遗留演示数据（INITIAL_*/MOCK_*，多数未再引用） |
| `hooks/useDismiss.ts` | 浮层统一点击外部关闭 |
| `index.css` | Tailwind 4 入口 + 暗色 custom-variant + 动效关键帧系统 |
