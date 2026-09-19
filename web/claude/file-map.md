# web 文件地图

```
web/
├── index.html                 # Vite 入口 HTML
├── package.json               # favapi-web-console；dev/build/lint/preview/clean
├── package-lock.json + pnpm-lock.yaml   # 双锁并存（历史原因）
├── tsconfig.json              # ES2022 / bundler / noEmit / @ 别名
├── vite.config.ts             # 代理 FAVAPI_BACKEND、port 3000、inspector 插件
├── public/site_icons/         # 平台图标（wechat 为 svg）
└── src/                       # 63 个 ts/tsx，约 15.6k 行
    ├── main.tsx               # StrictMode + HashRouter + App
    ├── App.tsx                # ~885 行编排层：视图切换/状态/轮询/Modal/Toast/AlertDialogHost
    ├── api.ts                 # ~1255 行接口封装 + 4 SSE + to* 映射
    ├── types.ts / primaryColor.ts / index.css / vite-env.d.ts
    ├── data/
    │   ├── platforms.ts       # 平台静态元数据（12 个，8 个 followsApi）
    │   └── mockFavData.ts     # 遗留 mock + PLATFORMS re-export
    ├── hooks/useDismiss.ts    # 浮层点击外部关闭
    └── components/
        ├── Sidebar / Header / AlertDialog(新) / ViewModeSwitch / TerminalDialog
        ├── Popover / DropdownSelect / SiteIcon / DevInspector
        ├── Dashboard/     DashboardView、StatCard、ActiveAccountCard、CalendarCard、
        │                 RecentCollectionCard、ScheduleQueueCard（6）
        ├── Accounts/     AccountsList、CreateAccountModal、QRCodeLoginModal、CookiesModal
        │   └── AccountDetail/  index、Header、InfoCards、PlatformOperations、
        │                       FolderPicker、ScrapeForm、ScrapeStream、TasksTab 等（13）
        ├── Data/         DataBrowserView(904行容器) + 拆出子组件：
        │                 BrowserFilterPanel、BrowserContent、BrowserToolbar、
        │                 DataItemCard、AiTaggingModal、useAiTagging、
        │                 BrowserTagModals、BrowserDeleteModals + ItemDetailModal、
        │                 ItemActionMenu、DownloadConfirmModal（12）
        ├── Follows/      FollowsView、AuthorPage、PlayerModal、FollowItemActions、
        │                 FollowsSyncButton、FollowAvatar、GroupEditDialog（7）
        ├── Tasks/TasksView.tsx
        ├── Schedule/ScheduleView.tsx
        ├── Downloads/    DownloadsView + NewDownloadModal（2）
        └── Settings/SettingsView.tsx   # ≈1025 行，全仓第一大组件
```

修改热点：加接口→api.ts+对应视图；抓取表单→ScrapeForm+api.formToParams；数据过滤→Data/BrowserFilterPanel+DataBrowserView；特别关注→Follows/ 族+api.ts follows 函数；平台操作→PlatformOperations（表单由后端 /platforms 的 api_operations 驱动）。
