# 测试与质量

## 测试命令

```bash
.venv/Scripts/python.exe tests/test_parser.py   # 解析器单测，4 用例
.venv/Scripts/python.exe tests/smoke_test.py    # API + 数据层冒烟，29 检查项
```

两者均自带 `__main__` runner（输出 PASS/FAIL 与退出码），也可被 pytest 收集（test_parser 的函数名 test_*）。无 CI 配置、无 lint/format 配置、无类型检查配置。

## 覆盖情况

| 测试 | 覆盖 | 不覆盖 |
|------|------|--------|
| test_parser.py | parse_aweme 字段映射 / 缺字段兜底 / listcollection 元信息 / 空响应 | — |
| smoke_test.py | 平台元信息、账号 CRUD 与 400/404 分支、抓取请求校验（禁用/平台不一致/未知账号/不支持 action/Bilibili 占位）、任务生命周期、收藏入库与去重、分页、删除账号级联（favorites 清空 contents 保留）、Web 4 页面渲染、OpenAPI | 真实浏览器链路（登录、实际抓取）——依赖人工在页面上验证 |

smoke_test 通过 `FAVAPI_DATA_DIR=临时目录` 隔离数据，用 `app.router.lifespan_context` + `httpx.ASGITransport` 与服务同事件循环驱动（aiosqlite 连接安全）。

## 真实链路验证方式（人工）

procm 启动 server → 浏览器开 `http://127.0.0.1:8300` → 创建抖音账号 → 登录扫码 → 账号详情页触发抓取 → 看「数据」「任务」页面。

## 已知质量风险 / 技术债

- requirements.txt 未锁版本，无 lock 文件；fastapi/pydantic 升级可能破坏 `TemplateResponse(request, name, context)` 新签名等用法（findings.md 有记录）。
- 抖音登录态判断是 cookie 存在性启发式（sessionid 非空即有效），失效只能在抓取时被动发现。
- `update_account` / `update_task` 用 f-string 拼 SQL 列名——列名来自 API 层白名单，新增调用方时必须保证字段名合法。
- 同步抓取持有 profile 锁最长 300s，期间该账号的 status 轮询会快速返回 busy（预期行为，非 bug）。
- 无鉴权：仅监听 127.0.0.1 时可接受，改 HOST 对外暴露前必须加认证。
- 响应内嵌 items 上限 100 条（`_MAX_ITEMS_IN_RESPONSE`），全量数据走 /favorites 分页。
