# Task Plan: 修复按收藏时间批量取消匹配失败

## Goal
修复 `cancel_collect_multi` 日期区间模式匹配 2025 年收藏始终为 0，并消除前端进度日志中的 `undefined`。

## Current Phase
Phase 8

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
- [x] 保存当前账号只读收藏分页到临时目录
- [x] 离线对比分页与精翻游标/条目
- [x] 修复并回归验证
- **Status:** complete

### Phase 5: 手动浏览器锁修复
- [x] 定位 API 操作未释放手动浏览器锁
- [x] 同步/SSE 操作入口关闭手动浏览器
- [x] 运行最终验证
- **Status:** complete

### Phase 6: 日期范围完整性
- [x] 识别 API 提前结束仍发送 done 的路径
- [x] 缺失游标/未到 date_from 时改为错误事件
- [x] 增加回归测试并验证
- **Status:** complete

### Phase 7: 统一按视频上传时间完整扫描
- [x] 检查真实单条收藏响应字段
- [x] 确认无加入收藏时间字段
- [x] 移除游标日期提前停止和范围错误
- [x] 完整扫描所有分页并按 create_time 匹配
- [x] 回归验证
- **Status:** complete

### Phase 8: 防止边扫边删导致漏页
- [x] 定位删除导致 cursor 跳过数据
- [x] 改为扫描与删除分离
- [x] 增加回归测试并验证
- **Status:** complete

### Phase 9: 调整取消接口批次上限
- [x] 设置单批最多 100 条
- [x] 保持抓取分页为 20 条
- [x] 完成静态检查
- **Status:** complete

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
