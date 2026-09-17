# web 文件地图

```
web/
├── index.html                 # Vite 入口 HTML
├── package.json               # favapi-web-console；dev/build/lint/preview/clean
├── package-lock.json + pnpm-lock.yaml   # 双锁并存（历史原因）
├── tsconfig.json              # ES2022 / bundler / noEmit / @ 别名
├── vite.config.ts             # 代理 FAVAPI_BACKEND、port 3000、inspector 插件
├── public/site_icons/         # 7 个平台图标（wechat 为 svg）
└── src/
    ├── main.tsx               # StrictMode + HashRouter + App
    ├── App.tsx                # ~830 行编排层：视图切换/状态/轮询/Modal/Toast
    ├── api.ts                 # ~910 行接口封装（12 分组 + 3 SSE + to* 映射）
    ├── types.ts               # UI 类型
    ├── index.css              # Tailwind 4 + 暗色 variant + 动效关键帧
    ├── vite-env.d.ts
    ├── data/
    │   ├── platforms.ts       # 平台静态元数据（11 个）
    │   └── mockFavData.ts     # 遗留 mock + PLATFORMS re-export
    ├── hooks/useDismiss.ts    # 浮层点击外部关闭
    └── components/
        ├── Sidebar / Header / DropdownSelect / SiteIcon / DevInspector
        ├── Dashboard/     DashboardView、StatCard、ActiveAccountCard、CalendarCard、
        │                 RecentCollectionCard、ScheduleQueueCard
        ├── Accounts/     AccountsList、CreateAccountModal、QRCodeLoginModal、CookiesModal
        │   └── AccountDetail/  index、Header、InfoCards、PlatformOperations、
        │                       FolderPicker、ScrapeForm、ScrapeStream、TasksTab、
        │                       ClearFavoritesModal、DeleteAccountModal
        ├── Data/         DataBrowserView(≈1990行)、DataItemCard、DownloadConfirmModal、
        │                 ItemActionMenu、ItemDetailModal
        ├── Tasks/TasksView.tsx
        ├── Schedule/ScheduleView.tsx
        ├── Downloads/DownloadsView.tsx
        └── Settings/SettingsView.tsx
```

修改热点：加接口→api.ts+对应视图；抓取表单→ScrapeForm+api.formToParams；过滤逻辑→DataBrowserView；平台操作→PlatformOperations（表单由后端 /platforms 的 api_operations 驱动）。
