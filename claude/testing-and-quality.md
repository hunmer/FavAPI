# 测试与质量

## 测试命令（Windows 路径；macOS 用 .venv/bin/python）

```bash
.venv/Scripts/python.exe tests/test_parser.py             # 抖音 parser 单测
.venv/Scripts/python.exe tests/test_bilibili_parser.py    # B 站 parser + 参数校验
.venv/Scripts/python.exe tests/test_xiaohongshu_parser.py # 小红书 parser
.venv/Scripts/python.exe tests/test_douyin_api_client.py  # 抖音 API client（unittest+mock）
.venv/Scripts/python.exe tests/test_youtube_platform.py   # 声明式 _walk + YouTube 样本解析
.venv/Scripts/python.exe tests/test_download_worker.py    # 下载 worker 单测
.venv/Scripts/python.exe tests/smoke_test.py              # API+数据层冒烟（临时数据目录，不依赖浏览器）
.venv/Scripts/python.exe tests/e2e_schedule_test.py       # 定时链路 e2e（需先起服务）
```

共 9 个测试脚本（含 __init__ 共 9 个 .py）。均带 `__main__` runner 也可 pytest 收集；无 pytest 配置文件、无 CI 测试 job（release.yml 只做打包）、无 lint/类型检查配置。

## 覆盖情况

| 测试 | 覆盖 |
|------|------|
| smoke_test | 平台元信息、账号 CRUD 与错误分支、抓取校验、任务记录、收藏入库回读（含 B 站同视频多收藏夹）、删号级联、Web 页面渲染 |
| e2e_schedule_test | 禁用账号 + 每分钟计划的触发与 next_run_at 推进 |
| 各 parser/api_client 单测 | 样本 JSON（samples/）驱动的纯函数测试 |

不覆盖：真实浏览器链路（登录、实际抓取）、下载子进程、AI 打标 LLM 调用——需人工验证。

## 真实链路人工验证

procm 起 server → `http://127.0.0.1:8300` → 创建账号 → 扫码登录 → 详情页触发抓取/平台操作 → 看「数据/任务/下载」。平台接入类改动参考 `handoff/` 下的验证脚本模式（`_adapter_verify.py` 全链路直测、`_ig_verify.py` cookie 走环境变量不落盘）；根目录 `verify_bili_*.py` 含真实 cookie 勿提交。`handoff/follows-platform-integration.md` 是 follows 多平台接入交接指南（注意其头部"基于 douyin+bilibili 双平台"描述已过时，现状 8 平台）。

## 已知质量风险 / 技术债

- 依赖未锁版本（fastapi/curl_cffi/xhshow 等），平台接口签名随时间失效的风险高（抖音写接口已须浏览器页面 fetch hook 加签）。
- 抖音/快手登录态判断是 cookie 存在性启发式，失效只能在抓取时被动发现。
- `update_*` 类 SQL 用 f-string 拼列名——列名必须来自白名单，新增调用方注意。
- 无鉴权：仅 127.0.0.1 监听可接受，对外暴露前必须加认证。
- 响应内嵌 items 上限 100 条摘要，全量走 /favorites 分页（limit≤5000）。
- codegraph 索引曾滞后于源码（新增平台未及时入索引），以 git 文件为准。
- App.tsx 内有 `[DBG-ACC]` console.warn 调试残留（见 web 侧）。
