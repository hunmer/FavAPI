# web 模块职责

## 顶层与通用组件（components/ 根级）

| 文件 | 职责 |
|------|------|
| `Sidebar.tsx` | 8 tab 竖直导航（motion 指示器）、下载 badge、主题切换、头像 |
| `Header.tsx` | 全局搜索、RunningFetchInfo 抓取进度指示、actions 槽（按 tab 注入 FollowsSyncButton / 新建下载） |
| `AlertDialog.tsx` | 全局 Alert/Confirm：命令式 `await confirmDialog()/alertDialog()` + 根部 `<AlertDialogHost />`（useSyncExternalStore；Esc=取消/Enter=确认/danger 红色） |
| `ViewModeSwitch.tsx` | grid/waterfall/list 分段控件 + `readViewMode(storageKey)`；Data 与 Follows/AuthorPage 共用 |
| `TerminalDialog.tsx` | 终端式输出弹窗 |
| `Popover.tsx` / `DropdownSelect.tsx` | 通用浮层 / 统一风格下拉选择器 |
| `SiteIcon.tsx` | 平台图标：静态映射 + 后端 icon_url 兜底 |
| `DevInspector.tsx` | dev 专用元素定位器（生产不渲染） |

## 功能域组件

| 目录 | 组件与职责 |
|------|-----------|
| `Dashboard/` | DashboardView 总布局；StatCard 数字滚动；ActiveAccountCard 一键同步；CalendarCard 收藏日历热力；RecentCollectionCard；ScheduleQueueCard |
| `Accounts/`（17 文件） | AccountsList 卡片网格与批量刷新身份；CreateAccountModal；QRCodeLoginModal 扫码登录状态机；CookiesModal；`AccountDetail/` 13 文件：index 组合页、Header 工具栏、InfoCards、PlatformOperations（表单由后端 api_operations 驱动，SSE 流式）、FolderPicker（B 站收藏夹批量管理）、ScrapeForm、ScrapeStream、TasksTab、关注列表挑选特别关注、确认弹窗等 |
| `Data/`（12 文件） | **DataBrowserView（904 行，状态与数据逻辑容器；已从 ≈1990 行拆分）**：过滤条件 localStorage 记忆 + URL 参数同步。拆出：BrowserFilterPanel（638 行左侧过滤面板）、BrowserContent（网格/瀑布流/列表+分页条）、BrowserToolbar（排序/视图切换/多选/AI 打标入口+BrowserSelectionBar）、DataItemCard（封面卡片）、AiTaggingModal+useAiTagging（AI 打标弹窗与 SSE hook）、BrowserTagModals（标签右键菜单/删除/建组）、BrowserDeleteModals（批量/单条删除确认）。另有 ItemDetailModal（详情+标签编辑+下载入队）、ItemActionMenu、DownloadConfirmModal（被 Follows 复用） |
| `Follows/`（7 文件） | 特别关注页面族：**FollowsView（332 行）** `/follows` 主路由（分组 pills、博主卡片网格、未读角标、单博主同步、编辑/删除菜单；内部正则派发作者子路由）；**AuthorPage（431 行）** `/follows/author/:secUid` 博主主页（信息头、仅看未读、三视图、分页 PAGE_SIZE=18、内嵌 AuthorPostCard）；**PlayerModal（338 行）** 播放弹窗（视频代理直链/YouTube iframe/图文轮播+BGM/信息 tab/打开即标已读/Esc 关闭）；**FollowItemActions（273 行）** 作品操作共享模块（原站 URL 模板、账号隔离打开、下载入队、FollowItemActionMenu 右键菜单 + FollowItemActionButtons 2x2 网格，被 Data 复用）；FollowsSyncButton（74 行，Header 一键更新：SSE 进度 N/M·新增 X、可取消）；FollowAvatar（本地化头像+首字符回退）；GroupEditDialog（分组编辑） |
| `Tasks/TasksView.tsx` | 任务列表：状态筛选、手动刷新、清空记录 |
| `Schedule/ScheduleView.tsx` | 计划列表（触发/启停/删除）、创建计划（cron、list_favorites/ai_tag）、AI Agent 配置管理；复用 CalendarCard |
| `Downloads/DownloadsView.tsx` + `NewDownloadModal` | 下载队列：3s 自轮询进度、重试/暂停/删除/文件管理器定位；新建下载弹窗 |
| `Settings/SettingsView.tsx` | 运行参数（profile/headless/间隔/超时/下载目录/并发）、主题与布局、头像上传、AI Agent CRUD+连通性测试（≈1025 行，全仓第一大组件） |

## 非组件模块（src/）

| 文件 | 职责 |
|------|------|
| `App.tsx`（约 885 行） | 编排层：8 视图切换、账号详情 `?account=` 双向同步、轮询、Toast、全局 Modal、AlertDialogHost |
| `api.ts`（约 1255 行） | 全部后端接口封装 + 4 个 SSE 流（fetch/operation/tag/followsSync）+ follows 14 函数 + mediaUrl/followPostCoverUrl/followAvatarUrl URL 构造 + formToParams 表单抹平 |
| `types.ts` | UI 类型：NavTab(8)、Account/AccountStatus、ScrapedItem、ScheduledSync 等 |
| `data/platforms.ts` | 平台静态元数据 PLATFORMS（12 个，含未实现 zhihu/weibo/twitter；8 个 `followsApi: true`）+ DEFAULT_FETCH_TARGETS 回退 |
| `data/mockFavData.ts` | re-export PLATFORMS + 遗留演示数据（多数未再引用） |
| `hooks/useDismiss.ts` | 浮层统一点击外部/右键/滚动关闭 |
| `primaryColor.ts` | 主题主色 |
| `index.css` | Tailwind 4 入口 + 暗色 custom-variant + 动效关键帧系统 |
