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

## Follow-up Findings
- 真实快照目录：`/tmp/favapi-collect-WVCEUA`，第 49 页 12 条与精翻非空 ID 集合完全一致；其中只有 1 条加入收藏时间在 2025 年。
- 精翻现在到原始 `count=20` 页尾后交回主分页，避免将整段空游标扫描显示为 2024-12-31。
- 第二次无输出的根因是 API 操作路由未调用 `browser.close_manual`；手动浏览器持有 profile 锁，cookie 读取无限等待。
- 新反馈显示扫描到 2022 年且游标未知仍发送 done；日期下界为 2021 时，接口未确认扫到下界，不应判定范围完整。
- 现在 `has_more=true` 且 cursor 缺失、或 API 结束时游标仍未到 `date_from`，都会抛出错误事件，不再发送 done。
- 用户提供的真实 aweme 数据中没有 `collect_time`、`collected_at` 或 `collect_date`；顶层仅有 `create_time=1783679495`，这是视频上传时间。
- `collect_stat`、`is_collects_selected`、`collect_count` 等是状态/计数，不是加入收藏时间。
- 按用户确认，日期取消现在统一完整扫描所有收藏分页，并按 parser 从 `create_time` 生成的条目时间匹配；移除了游标日期提前停止和“尚未扫描到起始日期”错误。
- 新反馈显示近 2000 条只扫描到 733 条；根因是每页立即删除命中视频，删除改变收藏列表后使后续 cursor 跳过大量条目。
- 现已改为两阶段：第一阶段完整扫描并去重命中 ID；第二阶段扫描结束后按 20 条批量取消。
- 用户确认取消收藏接口单次最多处理 100 条；已将取消批次上限调整为 100，抓取分页仍保持 20 条。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 为无效游标提供保守回退，不能丢弃当前页 | 取消操作不可逆，回退必须避免误删且不能静默漏页 |
| 前端按字段集合而非日期值判断进度类型 | `oldest_collected_at=null` 仍是合法的日期进度事件 |
| API 操作入口先关闭手动浏览器 | 与普通抓取入口一致，避免 profile 锁永久等待 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 没有现成的日期取消单元测试 | 新增 mock API 回归测试覆盖单位变化和无效游标 |
| 只读账号详情输出包含敏感 cookie | 停止使用该接口调试，不记录或展示其值 |

## Resources
- `web/src/components/Accounts/AccountDetail.tsx`
- `app/platforms/douyin/api_client.py`
- `app/platforms/douyin/adapter.py`
