# 文件地图

```
FavAPI/
├── main.py                     # 单实例锁 + uvicorn(daemon) + pywebview 窗口 + 更新就绪回调
├── requirements.txt            # 13 项依赖，未锁版本
├── FavAPI.spec                 # PyInstaller 打包配置
├── .tufup-repo-config          # tufup 更新仓库配置
├── .github/workflows/release.yml  # Win/mac 便携包发布流水线
├── procm-commands.json         # procm 命令（Win/mac 双套 + web）
├── AGENTS.md / CLAUDE.md       # 工作区规范 / AI 上下文索引
├── PRD.md / README.md / pages.md  # 需求 / 使用说明 / 前端页面规划
├── verify_bili_*.py            # 3 个含真实 cookie 的临时验证脚本
├── data/                       # 运行时（git 忽略）：favapi.db、profiles/、downloads/、uploads/、follow_*/
├── platforms/                  # 声明式平台配置（FAVAPI_PLATFORMS_DIR）
│   ├── kuaishou/platform.json  ├── tiktok/platform.json
│   ├── youtube/platform.json + favicon.ico
│   ├── threads/favicon.ico     # 纯 Python 适配器，目录仅图标
│   └── instagram/favicon.ico   # 同上
├── samples/                    # bilibili/douyin/kuaishou/wechat 收藏响应样本
├── scripts/                    # 抓包样本与辅助脚本
├── handoff/                    # AI 交接：接入 handoff 文档 + 真实链路验证脚本（勿当测试维护）
├── docs/api-fetch-integration-guide.md  # API 直连接入指南（9 平台现状）
├── web/                        # React SPA（独立索引 web/CLAUDE.md）
├── tests/                      # 9 个测试脚本（见 testing-and-quality.md）
└── app/                        # 87 个 .py
    ├── config.py               # 环境变量 + 常量
    ├── database.py             # 10 表 SCHEMA + Database 单例 + 迁移
    ├── models.py               # Pydantic 模型
    ├── server.py               # create_app + lifespan（db/残留清理/scheduler/download_worker/cover_worker）
    ├── taxonomy.py             # 内置标签分组体系
    ├── utils.py                # now_iso / new_id / 日期窗口
    ├── api/                    # 12 路由：accounts agents ai_tag covers downloads fetch follows
    │                           #          notifications queries schedules settings tags
    ├── services/               # 18 服务（见 module-responsibilities.md）
    ├── platforms/
    │   ├── base.py             # 适配器抽象 + ApiOperation + follows 可选方法
    │   ├── registry.py         # 注册表 + load_declarative（9 平台 + wechat）
    │   ├── declarative.py      # JSON 声明式适配器（capture/fields/scripts/proxy）
    │   ├── douyin/             # adapter + api_client + parser + constants（API 直连 curl_cffi）
    │   ├── bilibili/           # adapter + parser + constants（浏览器上下文直连）
    │   ├── xiaohongshu/        # adapter + api_client(xhshow) + parser + constants
    │   ├── kuaishou/           # adapter + api_client + sig_vm.js + sig4.cjs（Node 签名）
    │   ├── tiktok/             # adapter + api_client + constants
    │   ├── threads/            # adapter + api_client（GraphQL，需代理）
    │   ├── instagram/          # adapter + api_client + parser + constants（纯 API 直连，需代理）
    │   ├── youtube/            # adapter（纯 DOM 解析）
    │   └── wechat/             # adapter + parser（JSON 导入）
    └── web/router.py           # SPA 静态托管 web/dist（或"请先构建"提示页）
```

修改热点：抓取行为调参看各平台 `constants.py` 与根 `platforms/*/platform.json`；并发/超时看 `config.py`；查询过滤看 `data_store.py`；follows 媒体/资产看 `follow_store.py`；下载行为看 `download_worker.py`；发布打包看 `main.py` + `FavAPI.spec` + `release.yml`；前端页面看 `web/src/components/`。
