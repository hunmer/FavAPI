# web FAQ

**Q: 刷新 `/#/data` 之外的路径会 404 吗？**
不会，用的 HashRouter（`/#/...`），后端 StaticFiles 无需回退路由。这也是不用 BrowserRouter 的原因。

**Q: dev 模式请求全报 Network Error？**
后端没起（8300）。检查 `FAVAPI_BACKEND` 是否指向正确后端；dev server 在 3000，`/api` 全部代理。

**Q: 8300 首页提示"请先构建前端"？**
`web/dist` 不存在。`cd web && npm install && npm run build` 后重启/刷新。改了前端代码同样要重新 build 才会在 8300 生效。

**Q: 新平台在页面上没图标/显示奇怪？**
`public/site_icons/` 没有对应文件时 SiteIcon 回退后端 `/platforms/{name}/icon`（后端根 platforms/ 目录放 favicon.ico）。两处都没有则显示文字。

**Q: 平台操作按钮/表单从哪来？**
全部由后端 `GET /platforms` 的 `api_operations`（ApiOperation 声明）动态渲染，前端无硬编码；后端 reload 后前端刷新页面即可见。

**Q: 点击页面元素想定位源码？**
dev 模式悬浮 DevInspector 进入定位模式，点元素按注入的行号经 `/__open-stack-frame-in-editor` 打开编辑器（`REACT_EDITOR` 指定，默认 VS Code）。生产构建无此功能。

**Q: 暗色模式怎么切/在哪改样式？**
Sidebar 主题切换，class 式（`.dark`），Tailwind 4 经 `@custom-variant dark`；全局动效变量与关键帧在 `src/index.css`。

**Q: 收藏过滤是在前端还是后端做的？**
两者都有：服务端 `/favorites` 支持全部过滤参数；前端把 limit 5000 的数据拉回后在 DataBrowserView 内本地过滤/搜索。

**Q: 表单里 count/cursor/日期这些平台差异怎么处理？**
`api.ts` 的 `formToParams` 把统一表单值抹平成各平台 params（如 wechat 的 json_path、bilibili 的收藏夹目标），新增平台专属参数时在这里加。

**Q: 为什么有些组件读 localStorage？**
用户偏好持久化：主题、布局形态（fullPage）、平台操作表单上次填写值（按「账号+操作」键存），清缓存即重置。
