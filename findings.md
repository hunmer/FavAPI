# Findings & Decisions

## Requirements
- 2025-01-01 至 2026-01-01 应按收藏时间命中真实数据。
- 进度日志不得显示 `undefined`。
- 保持改动最小，并补充针对性验证。

## Research Findings
- 请求和 SSE 链路正常，共抓取 954 条、56 页，但匹配为 0。
- 第 50、54、55 页被前端按批次进度渲染，说明这些事件缺少 `oldest_collected_at`。
- `cancel_collect_by_window` 把响应 `cursor` 解释为微秒收藏时间；游标无效时 `page_lo=None`。
- 边界精翻遇到无效游标后会执行 `items=[]`，导致当前主分页的全部条目被跳过。
- 前端仅以 `oldest_collected_at` 是否存在区分日期/批次进度，所以日期模式的空游标页显示 `undefined`。
- 实际页面已拆分并使用 `web/src/components/Accounts/AccountDetail/PlatformOperations.tsx`；该文件现有未提交的 localStorage 表单持久化改动必须保留。
- 旧版实现仅按条目发布时间过滤；新版为支持收藏时间，引入了“20 条页游标区间 + 边界页 count=1 精翻”算法。
- 用户日志中无效游标后仍能继续分页，证明 `cursor` 并非只在末页为空；固定微秒阈值可能误判其他时间戳单位。
- 后端当前由 uvicorn `--reload` 运行，排除代码未重启导致行为滞后。
- 账号详情接口包含完整 cookies，不适合作为后续调试数据源；后续只使用非敏感本地统计和 mock。
- 真实只读分页显示：第 48 页游标为 2026-02-06；第 49 页有 13 条，游标直接到 2025-11-01，正好跨越 `date_to=2026-01-01`。
- 第 50-53 页分别到 2025-06、2025-05、2025-02、2024-12，但条目数为 0；因此 2025 年可见条目主要就在第 49 页。
- 用户执行日志的第 49 页仍显示 2026-02-06，证明边界页 `count=1` 精翻未推进，却把主分页第 49 页清空，直接漏掉 13 条。
- 实测 `count=1`：首次可返回 0 条，但游标从 2026-02-06 推进到 2026-02-05，下一次即恢复返回 1 条；因此 `if not items: break` 是直接根因。
- 新反馈显示修复后第 49 页日志仍跨到 2024-12-31，说明当前精翻进度展示的是“精翻最终游标”，不是原始边界页；且只命中 1 条，需要用真实快照比较 count=20/count=1 响应。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 为无效游标提供保守回退，不能丢弃当前页 | 取消操作不可逆，回退必须避免误删且不能静默漏页 |
| 前端按字段集合而非日期值判断进度类型 | `oldest_collected_at=null` 仍是合法的日期进度事件 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 没有现成的日期取消单元测试 | 新增 mock API 回归测试覆盖单位变化和无效游标 |
| 只读账号详情输出包含敏感 cookie | 停止使用该接口调试，不记录或展示其值 |

## Resources
- `web/src/components/Accounts/AccountDetail.tsx`
- `app/platforms/douyin/api_client.py`
- `app/platforms/douyin/adapter.py`
