# 砚田日耕 AI 系统详细技术设计

本目录细化 `../ai-technical-design.md`，后者仍是高层架构入口。

## 文档顺序

1. [数据模型与约束](./01-data-model.md)
2. [领域状态机](./02-state-machines.md)
3. [AI 工作流与领域命令](./03-ai-workflows-and-commands.md)
4. [API、异步协议与实施蓝图](./04-api-async-implementation.md)

## 共同约定

- 业务时区固定为 `Asia/Shanghai`；
- PostgreSQL 是唯一可信业务状态；
- 核心状态使用关系表，AI 快照、原始输出和命令 payload 使用 JSONB；
- 模型只能提出白名单领域命令，不能直接修改数据库；
- 多项目先完成用户周容量分配，再生成项目计划；
- active 项目允许因容量不足获得 0 分钟 unfunded 分配；不创建 WeekPlan/PlanningRun，展示“本周未排入容量”；
- paused 项目不占容量、不生成任务；轻量维持使用低预算 active 项目表达；
- 普通任务只归属周任务池，不生成普遍每日计划，也不设置任务数量业务上限；
- 截止日只使用 date；按通常可用星期和真实剩余天数折算截止前容量；
- AI 任务输出保持最小，order、due_date 和阻塞状态由后端生成或继承；TaskDependency 是阻塞事实来源；
- 周末延期写 deferred，下一周创建带 origin_task_id 的新任务；
- 容量重新分配创建不可变 AllocationSet revision，不原地覆盖旧预算；
- 周一先晋升安全执行基线，AI 只做增量修正；
- 下一预备周由确定性协调服务先创建计划壳，WeeklyReview 只填充任务；
- 重大变化使用 EventDrivenReplanning，并按 temporary/observe/structural/goal_change 分流；
- 自然语言反馈先按范围、紧急度和是否阻塞路由；普通 TaskEvent 不经过复杂规划工作流；
- 最近 2—3 周 ProjectWeekAssessment 支撑趋势，结构性确认后才进入 RemainingRouteCalibration；
- 截止风险绕过趋势窗口即时处理；到期后生成 ProjectClosureSnapshot，项目进入 closed 而非伪装成 completed；
- TaskEvent 一致性使用项目级 task_event_revision，不使用数据库 sequence 作为提交水位；
- 一次 PlanningRun 对应一个 ProposalSet，权限拆成多个原子 Proposal；
- PlanningRun running 使用可回收 lease，hard kill 后由扫描器 CAS 恢复；
- 租户关系由包含 user_id/project_id 的数据库复合外键兜底；
- 异步投递采用事务 Outbox 和至少一次投递；
- 历史里程碑冻结，不因后续任务重新计算。

## 文档权威

实现优先遵循以下顺序：

1. `../ai-system-design.md`：产品边界与运行规则；
2. `../ai-technical-design.md`：高层技术决策；
3. 本目录：字段、状态机、协议与实施细节。

若详细文档与高层文档冲突，应先修正文档，再实现代码，不能在代码中默默选择其中一种规则。
