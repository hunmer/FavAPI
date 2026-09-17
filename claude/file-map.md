# 文件地图

```
FavAPI/
├── main.py                     # uvicorn 一键启动（UTF-8 重配置）
├── requirements.txt            # 10 项依赖，未锁版本
├── procm-commands.json         # procm 命令（Win/mac 双套 + web）
├── AGENTS.md / CLAUDE.md       # 工作区规范 / AI 上下文索引
├── PRD.md / README.md / pages.md  # 需求 / 使用说明 / 前端页面规划
├── verify_bili_*.py            # 3 个含真实 cookie 的临时验证脚本
├── data/                       # 运行时（git 忽略）：favapi.db、profiles/、downloads/、uploads/
├── platforms/                  # 声明式平台配置（FAVAPI_PLATFORMS_DIR）
│   ├── kuaishou/platform.json  ├── tiktok/platform.json
│   ├── youtube/platform.json + favicon.ico
│   └── threads/favicon.ico     # threads 无 platform.json（纯 Python 适配器）
├── samples/                    # bilibili/douyin/kuaishou/wechat 收藏响应样本
├── scripts/                    # threads_saved_sample.json
├── docs/api-fetch-integration-guide.md  # API 直连接入指南
├── web/                        # React SPA（独立索引 web/CLAUDE.md）
├── tests/                      # 7 个测试脚本（见 testing-and-quality.md）
└── app/
    ├── config.py               # 环境变量 + 常量
    ├── database.py             # 8 表 SCHEMA + Database 单例 + 迁移
    ├── models.py               # Pydantic 模型
    ├── server.py               # create_app + lifespan（db/scheduler/download_worker）
    ├── taxonomy.py             # 内置标签分组体系
    ├── utils.py                # now_iso / new_id / 日期窗口
    ├── api/                    # 9 路由：accounts agents ai_tag downloads fetch queries schedules settings tags
    ├── services/               # 13 服务（见 module-responsibilities.md）
    ├── platforms/
    │   ├── base.py             # 适配器抽象 + ApiOperation 声明
    │   ├── registry.py         # 注册表 + load_declarative
    │   ├── declarative.py      # JSON 声明式适配器（capture/fields/scripts/proxy）
    │   ├── douyin/             # adapter + api_client + parser + constants（API 直连 curl_cffi）
    │   ├── bilibili/           # adapter + parser + constants（浏览器上下文直连）
    │   ├── xiaohongshu/        # adapter + api_client(xhshow) + parser + constants
    │   ├── kuaishou/           # adapter + api_client + sig_vm.js + sig4.cjs（Node 签名）
    │   ├── tiktok/             # adapter + api_client + constants
    │   ├── threads/            # adapter + api_client（GraphQL）
    │   ├── youtube/            # adapter（纯 DOM 解析）
    │   └── wechat/             # adapter + parser（JSON 导入）
    └── web/router.py           # SPA 静态托管 web/dist（或"请先构建"提示页）
```

修改热点：抓取行为调参看各平台 `constants.py` 与根 `platforms/*/platform.json`；并发/超时看 `config.py`；查询过滤看 `data_store.py`；下载行为看 `download_worker.py`；前端页面看 `web/src/components/`。
