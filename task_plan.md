# Task Plan: 修复按收藏时间批量取消匹配失败

## Goal
修复 `cancel_collect_multi` 日期区间模式匹配 2025 年收藏始终为 0，并消除前端进度日志中的 `undefined`。

## Current Phase
Phase 4

## Phases

### Phase 1: 定位数据与日期解析链路
- [x] 检查路由、操作实现和平台响应字段
- [x] 确认异常页事件结构
- **Status:** complete

### Phase 2: 最小修复
- [x] 修复空页但游标推进时的精翻逻辑
- [x] 修复精翻命中统计和进度事件显示兼容
- **Status:** complete

### Phase 3: 测试与交付
- [x] 增加或更新针对性测试
- [x] 运行静态检查和测试
- **Status:** complete

### Phase 4: 真实快照复现
- [ ] 保存当前账号只读收藏分页到临时目录
- [ ] 离线对比分页与精翻游标/条目
- [ ] 修复并回归验证
- **Status:** in_progress

## Key Questions
1. 收藏时间的真实响应字段与时间单位是什么？
2. 为什么部分 `progress` 事件没有日期管道字段？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 优先修复后端根因，前端只做事件兼容 | 匹配为 0 是业务错误，不能只修显示 |
| 精翻阶段先收集 ID，结束后再取消 | 避免取消操作改变收藏列表后导致后续游标跳项 |
| 空页只要游标有效且推进就继续 | 真实接口已验证 `count=1` 会返回空条目但新游标有效 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `.venv/bin/python -m pytest` 提示未安装 pytest | 1 | 回归测试改用标准库 unittest，不新增项目依赖 |
