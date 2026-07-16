# 后端与 AI 实施任务清单

本文将现有技术方案转换为可直接开发的后端与 AI 任务。任务按架构依赖排序；编号一经用于代码提交、测试证据或项目管理记录后不得重排或复用。

## 一、使用规则

- 实现权威顺序为 `../ai-system-design.md`、`../ai-technical-design.md`、本目录详细设计；若语义冲突，先登记“文档阻塞项”并修正文档，不得在代码中自行选择。
- 每个任务必须完成其“完成定义”，并通过 `06-backend-ai-checklist.md` 中同编号的全部检查项，才可标记完成。
- 交付物中的表、字段和目录名是职责边界；实际 SQLAlchemy、Pydantic 和应用服务可以在不改变领域语义的前提下拆分文件。
- 本文不记录负责人、优先级、工期或工作量；排期信息在项目管理工具中维护。

## 二、范围与跨任务不变量

### 2.1 本期范围

- FastAPI 模块化单体、PostgreSQL、Redis、Celery、Scheduler 和 Outbox Dispatcher；
- 身份、用户偏好、项目路线、用户周容量、周计划、任务、反馈和 AI 编排；
- InitialPlanning、WeeklyReview、FeedbackUnderstanding、EventDrivenReplanning、RemainingRouteCalibration、DeadlineClosure 和 CalibrationRecovery；
- REST/OpenAPI、异步轮询、领域命令、测试、AI 评测、可观测性、CI/CD 和上线容量验证。

### 2.2 明确不在本期范围

- 微信小程序、Web、App 及任何客户端 UI；
- 材料上传、对象存储、扫描、解析与 MaterialUnderstanding；
- 微信订阅消息、邮件、Push 和通知发送模块；
- 微服务拆分、Kubernetes、Kafka、向量数据库、自主多 Agent、实时流式规划和多模型自动路由。

### 2.3 必须始终成立的不变量

1. PostgreSQL 是唯一可信业务状态；Redis、Broker 和模型输出都不能成为业务真相。
2. AI 只能产生白名单领域命令，不能直接写数据库、输出 JSON Patch 或降低确定性权限等级。
3. `UserWeekAllocationSet` 通过不可变 revision 演进，重新分配不得覆盖旧版本。
4. TaskEvent 一致性使用项目级 `task_event_revision`，数据库 sequence 不作为提交水位。
5. 事务锁顺序固定为 Capacity → AllocationSet → Allocation → Project → WeekPlan → Task/Milestone。
6. 异步投递使用事务 Outbox 和至少一次投递；Worker、Dispatcher、Scheduler 均须幂等和可安全重入。
7. 周一先晋升确定性安全基线；AI 失败、超时或不可用不得清空最后一个已生效计划。
8. 所有业务日期按 `Asia/Shanghai` 解释，数据库时间戳存 UTC，截止日只使用 date。
9. 所有跨租户、跨项目关系由应用层校验和数据库复合外键共同保护。

---

## 三、阶段 1：工程基础

### TASK-001 工程骨架、依赖与本地环境

**目标**：建立可启动、可测试、边界清晰的 Python 模块化单体。

**前置依赖**：无。

**实施要点**：

- 建立 `backend/app`、`backend/migrations` 和 `backend/tests/{unit,integration,contract,evaluation,e2e}`；按详细设计建立 identity、planning、tasks、feedback、ai_orchestration 与共享 infrastructure 边界。
- 配置 FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、PostgreSQL、Redis、Celery、pytest、Ruff、mypy/pyright 和 Docker。
- 提供 Local/Test 配置及本地 PostgreSQL、Redis 的可重复启动方式；生产密钥不得进入仓库。
- 增加架构依赖检查，禁止领域层导入 FastAPI、Celery、SQLAlchemy model 或供应商 SDK。

**交付物**：可启动 API、数据库迁移入口、测试入口、本地基础设施配置和模块边界检查。

**完成定义**：干净环境可启动 API、连接 PostgreSQL/Redis、执行空迁移和测试；领域层依赖规则进入 CI。

**关联检查项**：`CHECK-001-*`。

**技术方案来源**：`../ai-technical-design.md` 二、三、四、十四；`04-api-async-implementation.md` 九、十、十一。

### TASK-002 配置、Clock、错误模型与可观测性基座

**目标**：统一时间、配置、错误和关联追踪，避免业务代码直接依赖系统时间或展示文案。

**前置依赖**：TASK-001。

**实施要点**：

- 实现可注入 Clock，业务周、业务日期和截止判断固定使用 `Asia/Shanghai`，时间戳统一转 UTC。
- 实现启动配置校验、非敏感配置/密钥/版本化策略/Prompt 配置的分层读取；关键配置缺失时启动失败。
- 实现统一成功响应和错误 Envelope，稳定 `error.code`、`retryable`、`correlation_id` 与安全的 `details`。
- 建立结构化日志、请求关联 ID 和健康/就绪检查基座，不记录 token、原始敏感正文或内部堆栈到客户端。

**交付物**：Clock 接口及实现、配置模型、错误类型与异常映射、关联日志中间件、健康检查。

**完成定义**：冻结时钟可覆盖跨周/跨年测试；配置错误阻止启动；所有异常按统一协议返回且可通过 correlation ID 追踪。

**关联检查项**：`CHECK-002-*`。

**技术方案来源**：`04-api-async-implementation.md` 一、七、十；`../ai-technical-design.md` 十二、十三、十四。

---

## 四、阶段 2：身份、偏好与租户隔离

### TASK-003 用户、身份、设备会话与令牌轮换

**目标**：实现内部 User 与平台身份分离、可撤销的设备会话和安全的 refresh token 轮换。

**前置依赖**：TASK-001、TASK-002。

**实施要点**：

- 迁移并实现 `users`、`user_identities`、`user_devices`、`auth_sessions`、`refresh_tokens`；refresh token 仅保存哈希和轮换链。
- 实现微信 code 登录的 provider 适配边界、access/refresh 签发、单设备撤销、全部退出与 `auth_version/session_version` 校验。
- refresh 时在同一事务锁定 Session 与当前 Token；旧 token 重放必须撤销整个会话。
- 暂不实现客户端登录 UI；测试使用假微信 provider，不依赖外部网络。

**交付物**：身份迁移、仓储/应用服务、认证依赖以及 `/auth/wechat/login`、`/auth/refresh`、`/auth/logout`、会话查询/撤销接口。

**完成定义**：正常轮换只产生一个有效后继 token；重放、撤销和版本变化立即使对应 access/refresh token 失效。

**关联检查项**：`CHECK-003-*`。

**技术方案来源**：`01-data-model.md` 三；`04-api-async-implementation.md` 1.5、2.1。

### TASK-004 用户偏好、API 幂等基座与租户保护

**目标**：实现用户容量偏好、写请求幂等和数据库级租户隔离基础能力。

**前置依赖**：TASK-003。

**实施要点**：

- 实现 `user_preferences`、`api_idempotency_records` 及 preference revision 条件更新。
- 对要求幂等的 POST 保存规范化 method/path、请求摘要、处理租约和首次完成响应；相同 key/相同请求返回首次响应，不重新执行。
- 同一用户 key 搭配不同请求返回 `IDEMPOTENCY_KEY_REUSED`；不同用户可独立使用相同 key。
- 为后续业务表准备包含 `user_id`、必要时包含 `project_id` 的复合候选键/外键规范和统一 ownership 查询策略。

**交付物**：偏好迁移与接口、幂等中间件/应用服务、租户复合键迁移约定。

**完成定义**：偏好并发写产生明确 revision 冲突；幂等重试无重复副作用；伪造其他用户 ID 在应用层或数据库层被拒绝。

**关联检查项**：`CHECK-004-*`。

**技术方案来源**：`01-data-model.md` 3.6、8.8、10.6；`04-api-async-implementation.md` 1.4、2.1。

---

## 五、阶段 3：项目与路线

### TASK-005 Project、Stage、Milestone 与关闭快照

**目标**：实现项目路线的可信持久化模型、约束和读模型。

**前置依赖**：TASK-004。

**实施要点**：

- 迁移并实现 `projects`、`stages`、`milestones`、`project_closure_snapshots`，包含 project/route/task-event revisions、目标日期策略和终态原因。
- 保证每项目同一时间仅一个主推进 Milestone；历史 `advanced/superseded/closed` 节点冻结。
- 实现路线查询，严格区分 current、冻结 history 和 tentative future；终态项目保留只读路线与关闭快照。
- 创建继任项目只允许引用同用户且 `closed` 的前项目，不复制旧任务。

**交付物**：领域对象、迁移、仓储、路线查询服务及 Project/Route 读取接口。

**完成定义**：唯一约束、排序、冻结语义和跨租户引用由集成测试证明；路线接口无重复 current/history/future 对象。

**关联检查项**：`CHECK-005-*`。

**技术方案来源**：`01-data-model.md` 四、十；`02-state-machines.md` 二；`04-api-async-implementation.md` 2.2。

### TASK-006 项目状态机与确定性终态操作

**目标**：实现 draft/planning/active/paused/completed/closed/archived 的合法转换及事务副作用边界。

**前置依赖**：TASK-005。

**实施要点**：

- 将状态迁移集中在领域状态机和应用服务，拒绝控制器或 ORM 任意赋值。
- 实现项目创建、允许直接编辑的非目标字段、pause/resume、用户确认 complete 和 archive。
- `complete` 仅允许 active 项目，记录 `terminal_reason=user_completed`；到期但未确认达成不得伪装为 completed。
- 为 pause/resume/complete 定义后续与容量、计划、任务、运行和 Proposal 协作的原子接口，具体副作用在后续任务接入。

**交付物**：Project 状态机、命令服务、相关 REST 接口和错误映射。

**完成定义**：所有合法转换、非法转换、幂等重试和并发 revision 冲突都有自动化测试；不存在绕过状态机的业务写路径。

**关联检查项**：`CHECK-006-*`。

**技术方案来源**：`02-state-machines.md` 2.1；`04-api-async-implementation.md` 2.2、四。

---

## 六、阶段 4：容量、周计划与任务事实

### TASK-007 用户周容量、分配版本与协调运行

**目标**：实现多项目规划前的用户周容量分配真相。

**前置依赖**：TASK-004、TASK-006。

**实施要点**：

- 实现 `user_week_capacities`、`user_week_allocation_sets`、`user_week_allocations`、`user_week_runs` 及汇总字段。
- AllocationSet 只追加 revision；同用户同周最多一个 active set，旧版本保留审计且不得原地修改。
- active 项目容量不足可获得 `unfunded/0`；paused 项目不参与分配；预算总和不得超过安全可分配容量。
- 实现 rollover/reallocation/recovery 幂等键、partial_failed 恢复语义和 Capacity → Set → Item 的锁序。

**交付物**：容量/分配迁移、领域策略、协调服务、用户周读取接口。

**完成定义**：并发分配无法产生两个 active set 或超配；unfunded 有 Allocation item 但没有 WeekPlan/PlanningRun。

**关联检查项**：`CHECK-007-*`。

**技术方案来源**：`01-data-model.md` 五、10.3；`02-state-machines.md` 三；`04-api-async-implementation.md` 2.3、5.1。

### TASK-008 WeekPlan、Task、依赖与 TaskEvent 投影

**目标**：实现周任务池、任务状态事实和可追溯事件投影。

**前置依赖**：TASK-005、TASK-007。

**实施要点**：

- 实现 `week_plans`、`tasks`、`task_dependencies`、`task_events`；普通 Task 只归属周任务池，不创建每日计划。
- TaskDependency 是阻塞事实来源，拒绝硬依赖环；`is_blocked` 和未满足前置摘要查询时派生。
- TaskEvent 事务更新 Task 投影、version、Project.task_event_revision 及周/分配/容量汇总；`actual_minutes` 是累计覆盖值，不按事件相加。
- 支持完成、撤销、跳过、恢复跳过、记录耗时；reopened/deferred 保留原周投入，延期新任务使用 `origin_task_id`。

**交付物**：任务迁移、状态机、事件应用服务和任务查询/事件写入接口。

**完成定义**：重复事件幂等；并发 expected version 仅一方成功；事件 revision 按提交序列无漏读；周任务查询不以业务上限截断。

**关联检查项**：`CHECK-008-*`。

**技术方案来源**：`01-data-model.md` 六；`02-state-machines.md` 四、五；`04-api-async-implementation.md` 2.4、5.3。

---

## 七、阶段 5：领域规则、revision 与并发

### TASK-009 容量、截止与周边界策略

**目标**：实现不依赖 AI 的容量、截止前可行性和自然周规则。

**前置依赖**：TASK-002、TASK-007、TASK-008。

**实施要点**：

- 按有效可用日计算 event_exclusive/date_inclusive 截止容量；拒绝当前周早于业务日期的 due date。
- 对所有项目 existing unfinished + proposed required tasks 按 cutoff 累计校验，不能只校验单项目或新增任务。
- 使用 `effective_consumed` 与 `remaining_estimated` 派生规则，避免预计量和实际量双计。
- 校验用户周总量、项目 allocation 预算、通常可用日为 0、跨月/跨年周和残周边界。

**交付物**：纯领域策略、错误 details、安全的预检接口和单元测试矩阵。

**完成定义**：算法与详细设计伪代码一致；边界测试覆盖多项目、多个 cutoff、部分投入、超预计投入和零可用日。

**关联检查项**：`CHECK-009-*`。

**技术方案来源**：`01-data-model.md` 10.3、10.4；`04-api-async-implementation.md` 5.4。

### TASK-010 revision 向量、冻结保护与统一锁序

**目标**：让并发应用只校验相关变化，同时从数据库层避免越界写和死锁分支。

**前置依赖**：TASK-005、TASK-007、TASK-008、TASK-009。

**实施要点**：

- 分别维护 route、plan、project、preference、allocation 和 project task-event revisions；禁止用单一总 revision 替代。
- 实现 expected versions 校验和稳定错误码；TaskEvent 后续相关事件使命令失效，无关事件不应误杀 Proposal。
- 所有聚合写服务遵循统一锁序；历史 WeekPlan 使用其原绑定 allocation，而非当前 active set。
- 数据库触发器/约束或仓储写保护拒绝冻结 Milestone 变更和跨租户关联。

**交付物**：revision 值对象/校验器、统一锁仓储方法、冻结保护和并发测试夹具。

**完成定义**：并发 Proposal/TaskEvent/容量写无超配、无丢更新；人为反序锁路径在静态或测试阶段被发现。

**关联检查项**：`CHECK-010-*`。

**技术方案来源**：`01-data-model.md` 十；`02-state-machines.md` 十一；`../ai-technical-design.md` 9.2、9.3。

---

## 八、阶段 6：REST 契约

### TASK-011 核心资源 API、OpenAPI 与错误契约

**目标**：落实现有 `/api/v1` 核心后端 API，不创造新的业务语义。

**前置依赖**：TASK-003 至 TASK-010。

**实施要点**：

- 实现 Auth/User、Projects/Route、UserWeek/WeekPlan、Tasks/TaskEvent 的详细设计接口。
- 使用 Pydantic 2 明确请求/响应、enum、UTC timestamp、业务 date、UUID 和游标分页；客户端分支只依赖 code/enum。
- 修改操作使用 `If-Match` 或请求 revision；创建/确认/事件 POST 强制 `Idempotency-Key`。
- 固化 OpenAPI 基线和兼容性检查；错误 details 不泄露其他用户 ID、模型原始输出或内部堆栈。

**交付物**：FastAPI 路由、Schema、OpenAPI 文件/快照、契约测试。

**完成定义**：API 清单中的本期接口均可调用；状态码、错误码、幂等与 revision 行为和详细设计一致。

**关联检查项**：`CHECK-011-*`。

**技术方案来源**：`04-api-async-implementation.md` 一、二、四。

### TASK-012 PlanningRun 轮询与 Proposal 决策 API

**目标**：提供稳定的异步运行查询和原子 Proposal 决策协议。

**前置依赖**：TASK-011；数据存储由 TASK-013、TASK-017 补全。

**实施要点**：

- 实现 PlanningRun、ProposalSet、Proposal 查询和 Proposal decision 接口的 Schema/路由边界。
- 异步创建返回 `202`、`status_url`、`poll_after_ms`；只在可靠计算时返回进度 percent，终态停止轮询。
- 决策请求校验 expected status、expires_at、revision vector 和命令前置条件；失败不得部分应用。
- GoalChange 使用独立 candidate confirm 协议并复用 Proposal/Decision 持久化，不创建独立 GoalChange 表。

**交付物**：轮询/决策 API 契约、状态响应映射、冲突错误和契约测试。

**完成定义**：pending/running/retry/terminal 映射稳定；过期、失效、版本冲突和幂等重试均返回规定结果。

**关联检查项**：`CHECK-012-*`。

**技术方案来源**：`04-api-async-implementation.md` 2.5、2.6、三、四。

---

## 九、阶段 7：可靠异步基础设施

### TASK-013 PlanningRun、Outbox 与可靠投递

**目标**：实现业务事务到 Broker 的可靠、可审计投递。

**前置依赖**：TASK-001、TASK-004、TASK-010。

**实施要点**：

- 实现 `planning_runs`、`outbox_messages` 和永久幂等 run key/generation；业务事务只写数据库，不直接 publish。
- Dispatcher 使用 `FOR UPDATE SKIP LOCKED` 批量 claim、30 秒 lease、Broker confirm、退避和 dead 状态。
- Celery payload 只传 ID/路由元数据，不传 Snapshot、用户材料或完整业务正文。
- published 只表示进入 Broker，不得覆盖已 running/succeeded 的 PlanningRun。

**交付物**：迁移、Outbox 仓储、Dispatcher 进程、队列路由和集成测试。

**完成定义**：提交与投递之间无丢消息窗口；多 Dispatcher、claim 超时和重复发布不会产生重复业务副作用。

**关联检查项**：`CHECK-013-*`。

**技术方案来源**：`01-data-model.md` 8.1、8.9；`02-state-machines.md` 六、八；`04-api-async-implementation.md` 6.1、6.2。

### TASK-014 Worker lease、重试、恢复扫描与 Scheduler

**目标**：保证 Worker 硬退出、超时和重复调度后 PlanningRun 可恢复且旧结果不能提交。

**前置依赖**：TASK-013。

**实施要点**：

- Worker 用 CAS 领取 pending/queued/retry_wait，写 lease owner/expiry/heartbeat；仅当前 lease owner 可写终态。
- 实现软/硬超时、acks_late、worker lost 重投、可重试/不可重试分类、指数退避和最大业务尝试。
- Scheduler 每分钟回收过期 running、投递到期 retry_wait，并以 CAS 转 retry_wait/dead；旧 Worker 必须放弃结果。
- Scheduler 固定上海时区、默认单活；扫描逻辑依赖唯一约束和 SKIP LOCKED 可演进多实例。

**交付物**：Worker 基类、lease/heartbeat、恢复扫描器、Scheduler 进程和故障注入测试。

**完成定义**：硬杀 Worker 后运行自动恢复或进入 dead；旧 Worker 无法覆盖新 Worker/终态；重复扫描不产生重复运行。

**关联检查项**：`CHECK-014-*`。

**技术方案来源**：`02-state-machines.md` 六、十；`04-api-async-implementation.md` 六、七。

---

## 十、阶段 8：AI 契约与验证

### TASK-015 Snapshot、稳定别名与证据引用

**目标**：为每次工作流构建最小、版本化、可审计的输入快照。

**前置依赖**：TASK-010、TASK-013。

**实施要点**：

- 实现 `planning_snapshots`、`model_invocations` 和各工作流 Snapshot Pydantic Schema。
- 只暴露 `current_milestone`、`task_3` 等运行内稳定别名；真实 ID 映射保存在可信侧。
- Snapshot 记录相关 revision、各项目 task event 水位、配置/Prompt/Schema 版本和证据索引。
- 上下文遵循最小化：当前路线、两周窗口、最近详细记录和 2—3 周结构化趋势；不发送无关全量历史。

**交付物**：ContextBuilder、Snapshot Schema/持久化、别名解析器和证据校验器。

**完成定义**：别名不可跨运行/租户解析；缺失、伪造和过期 evidence ref 被拒绝；同输入可重建可比较快照。

**关联检查项**：`CHECK-015-*`。

**技术方案来源**：`03-ai-workflows-and-commands.md` 二；`01-data-model.md` 8.2、8.3。

### TASK-016 ModelGateway、响应 Envelope 与验证流水线

**目标**：隔离模型供应商并确保任何模型输出在进入业务层前经过完整验证。

**前置依赖**：TASK-015。

**实施要点**：

- 定义单一 ModelGateway 接口、假网关和一个主供应商适配器边界；业务代码不得导入供应商 SDK。
- 实现工作流独立 Prompt、JSON Schema、超时、模型配置和 ModelInvocation token/费用/延迟/错误记录。
- 验证顺序固定为 Envelope/Schema → 别名/证据 → 白名单命令 → expected state/revision → 权限 → 容量/截止 → 冲突模拟。
- 拒绝数据库 ID、非白名单命令、任意 JSON Patch、越权权限、依赖环和超容量输出；信息不足时保守返回 clarification。

**交付物**：ModelGateway、假模型、响应 Schema、验证器链和标准化模型错误。

**完成定义**：常规测试完全离线；所有非法样本在落业务数据前失败；供应商故障不破坏现有计划。

**关联检查项**：`CHECK-016-*`。

**技术方案来源**：`03-ai-workflows-and-commands.md` 三、四、九、十；`../ai-technical-design.md` 6.4、13.3。

---

## 十一、阶段 9：Proposal 与首次规划

### TASK-017 ProposalSet、原子 Proposal、领域命令与权限拆批

**目标**：将一次模型响应转换为可审计、可原子应用的可信命令批次。

**前置依赖**：TASK-010、TASK-012、TASK-016。

**实施要点**：

- 实现 `planning_proposal_sets`、`planning_proposals`、`domain_commands`、`proposal_decisions`。
- 每个 PlanningRun 最多一个 ProposalSet；后端计算权限，将自动/确认/讨论命令拆成独立原子 Proposal。
- 低风险批次应用后，为待确认批次使用新版本重新生成依赖；每个 Proposal 全批成功或全批回滚。
- 应用事务按统一锁序重新校验状态、过期、revision、相关 TaskEvent、命令前置、容量与截止，再记录 Decision/Outbox。

**交付物**：Proposal 聚合、命令注册表/处理器、权限引擎、原子应用服务。

**完成定义**：重复应用无副作用；自动批次不会使确认批次自相冲突；任何命令失败时整个 Proposal 回滚。

**关联检查项**：`CHECK-017-*`。

**技术方案来源**：`01-data-model.md` 8.4—8.7；`02-state-machines.md` 七；`03-ai-workflows-and-commands.md` 四、五、七；`04-api-async-implementation.md` 5.2。

### TASK-018 GoalUnderstanding 与 InitialPlanning 闭环

**目标**：实现从 draft 项目到经确认的路线、容量分配和两周计划的首个完整后端闭环。

**前置依赖**：TASK-007 至 TASK-017。

**实施要点**：

- 实现 GoalUnderstanding 的缺失信息判断和目标日期策略规范化；信息不足不得编造计划。
- InitialPlanning 只生成 CreateStage/CreateMilestone/CreateWeekPlan/CreateTask，任务输出保持最小，order/due/阻塞由后端派生。
- 确认时按上海业务日期锁定受影响 UserWeekCapacity，先分配用户周预算，再在项目预算内原子创建路线和计划。
- 已有项目时只重分配未锁定容量；容量不足时缩减、unfunded 或形成需要确认的优先级候选，不得抢占锁定预算。

**交付物**：两个工作流、发起接口接线、确认应用服务和后端 E2E 测试。

**完成定义**：成功路径可从项目创建运行到 active 路线/任务；信息不足、模型失败、版本冲突和容量不足均保留一致状态且可恢复。

**关联检查项**：`CHECK-018-*`。

**技术方案来源**：`03-ai-workflows-and-commands.md` 5.1、8.1、8.2；`../ai-technical-design.md` 7.1。

---

## 十二、阶段 10：周滚动

### TASK-019 周一安全基线与 AllocationSet 滚动

**目标**：在不调用模型的前提下，按用户周原子晋升可执行基线并创建下一周规划壳。

**前置依赖**：TASK-007、TASK-008、TASK-013、TASK-014。

**实施要点**：

- 实现 Scheduler 和 `/user-weeks/current/ensure-active` 共享的 rollover 幂等事务。
- 晋升所有符合条件且已有 prepared 的计划；预算大于 0 但缺壳时创建空 active baseline 并记录 anomaly。
- 创建下一周 Capacity/AllocationSet；只为 active、funded、非 deadline-week、非 calibration-hold 项目创建 prepared 壳和 WeeklyReview Outbox。
- unfunded 无 WeekPlan/PlanningRun；paused 不参与；单项目失败不回滚其他项目已晋升基线。

**交付物**：UserWeekCoordinator rollover 服务、兜底 API、调度扫描和并发集成测试。

**完成定义**：同一用户周无论后台与首次打开并发触发多少次都只晋升一次；AI 全部超时时仍可读取和执行安全基线。

**关联检查项**：`CHECK-019-*`。

**技术方案来源**：`02-state-machines.md` 三、四；`04-api-async-implementation.md` 2.3、5.1、7.2。

### TASK-020 WeeklyReview、残周窗口与暂停重分配

**目标**：在既有预算壳内增量滚动任务，并正确处理残周创建和项目暂停/恢复。

**前置依赖**：TASK-017、TASK-018、TASK-019。

**实施要点**：

- WeeklyReview 读取执行周、prepared 壳和评估，只填充/调整已存在计划，不创建越过 allocation 的窗口。
- 首次规划残周不少于 4 天创建当前+下一周；少于 4 天额外创建下下周，当前周只放 1—2 个启动任务。
- 周末 planned 遗留写 deferred，并在新周创建带 origin 的剩余任务；历史里程碑保持冻结。
- pause 在单个用户周重分配事务释放未锁定预算、supersede 当前/未来计划、取消未开始任务并失效运行/Proposal；resume 重新获得正预算后才建壳和运行。

**交付物**：WeeklyReview 工作流、残周协调策略、pause/resume 完整副作用接线。

**完成定义**：两类残周窗口、延期追踪、暂停释放和恢复无预算分支均有端到端后端测试；任何项目不能越过用户周容量。

**关联检查项**：`CHECK-020-*`。

**技术方案来源**：`03-ai-workflows-and-commands.md` 8.3；`04-api-async-implementation.md` 2.2、十二；`../ai-technical-design.md` 7.2。

---

## 十三、阶段 11：反馈、重规划与结算

### TASK-021 Feedback、趋势评估与事件驱动重规划

**目标**：将自然语言反馈先确定性路由，再按影响范围触发最小必要工作流。

**前置依赖**：TASK-008、TASK-016、TASK-017、TASK-020。

**实施要点**：

- 实现 `user_feedback`、`project_week_assessments`、反馈保存/查询/确认和对话最小后端接口。
- FeedbackUnderstanding 输出 impact_scope、impact_nature、urgency、execution_blocked；执行事实转 TaskEvent，轻微感受转 observe。
- 用户级容量变化先由 UserWeekRun 建新 AllocationSet，再派生项目运行；项目 Worker 不得各自修改共享容量。
- EventDrivenReplanning 按 temporary/observe/structural/goal_change 分流；普通 TaskEvent 不调用复杂规划工作流。

**交付物**：反馈迁移、分类工作流、确定性路由器、项目/用户级重规划协调服务。

**完成定义**：完成事实、阻塞、轻微困难、用户容量和目标变化样本走正确分支；重复反馈和并发分类不产生重复运行。

**关联检查项**：`CHECK-021-*`。

**技术方案来源**：`01-data-model.md` 6.5、6.6；`03-ai-workflows-and-commands.md` 8.4、8.8；`../ai-technical-design.md` 7.3。

### TASK-022 路线校准、GoalChange 与 DeadlineClosure

**目标**：实现结构性路线调整、目标级用户确认、截止风险与确定性项目结算。

**前置依赖**：TASK-006、TASK-009、TASK-017、TASK-021。

**实施要点**：

- 最近 2—3 周 ProjectWeekAssessment 支撑趋势；结构性信号确认后才运行 RemainingRouteCalibration，跨 Stage 调整必须用户确认。
- GoalChange 候选使用系统命令和 ProposalDecision；接受时校验 project/preference revisions，拒绝只记决策。
- 每日截止风险扫描绕过趋势窗口立即触发 EventDrivenReplanning；paused 项目仅更新风险提示。
- target_date 已过时确定性执行 DeadlineClosure：Project→closed、冻结/关闭路线、取消 planned 任务、生成唯一 ClosureSnapshot、取消运行并失效 Proposal；DeadlineClosure 优先于并发规划写入。

**交付物**：校准/恢复工作流、GoalChange 应用服务、截止风险和关闭扫描器、并发测试。

**完成定义**：completed/closed 语义不可混淆；重复关闭仅一个快照；并发 Worker/Proposal 不能在关闭后提交旧结果。

**关联检查项**：`CHECK-022-*`。

**技术方案来源**：`03-ai-workflows-and-commands.md` 六、8.5—8.7；`04-api-async-implementation.md` 2.2、7.2。

---

## 十四、阶段 12：质量、运行与发布

### TASK-023 测试体系、AI 评测集与 CI 质量门

**目标**：把领域、数据库、契约、AI 和时间边界规则变成每次合并必须通过的自动化门禁。

**前置依赖**：TASK-001 至 TASK-022。

**实施要点**：

- 建立 unit/integration/contract/evaluation/e2e 分层；集成测试使用真实 PostgreSQL/Redis，常规 AI 测试使用假模型。
- 核心评测集覆盖四类目标、低容量、多项目竞争、信息不足、越权、不可达目标、截止超限、依赖环、事件重规划和跨 Stage。
- CI 执行 Ruff/格式、类型、单元、PostgreSQL/Redis 集成、Alembic 前进、OpenAPI 兼容、JSON Schema、安全/密钥扫描、AI 评测和 Docker 构建。
- 失败输出保留随机种子、Prompt/Schema/模型配置版本和可复现输入；禁止真实外网成为常规 CI 前提。

**交付物**：测试夹具/案例集、CI 配置、契约基线、评测报告格式。

**完成定义**：十项质量门全部自动执行且失败阻止合并；关键规则可从任务追踪到测试和证据。

**关联检查项**：`CHECK-023-*`。

**技术方案来源**：`../ai-technical-design.md` 十三；`04-api-async-implementation.md` 十一。

### TASK-024 可观测性、压测、迁移与发布基线

**目标**：证明核心后端在目标规模、依赖故障和滚动发布下可观察、可恢复、可安全上线。

**前置依赖**：TASK-014、TASK-022、TASK-023。

**实施要点**：

- 串联 API、UserWeekRun、PlanningRun、ModelInvocation、Proposal 和 Outbox correlation ID；记录延迟、重试、费用、队列积压、最老消息、dead、lease 超时和基线晋升指标。
- 告警覆盖 Dispatcher/Scheduler 心跳、队列积压、dead 消息、周滚动成功率、供应商限流和每日成本预算。
- 压测 1 万用户×平均 3 active 项目的周一晋升、100 并发 Proposal、重复投递、积压恢复、多 Dispatcher claim 和模型超时 30 分钟降级。
- 数据库变更遵循 expand/contract；验证旧代码兼容、滚动部署、回滚边界、备份恢复和启动密钥校验。

**交付物**：指标/告警/看板定义、压测脚本与报告、迁移演练记录、发布/回滚 Runbook。

**完成定义**：上线容量目标基于测量记录；模型/Redis/Worker/外部平台故障时已生效路线和任务仍可读、任务事件仍按允许范围写入，恢复后可幂等续跑。

**关联检查项**：`CHECK-024-*`。

**技术方案来源**：`../ai-technical-design.md` 十二、十四；`04-api-async-implementation.md` 六、十一、十三。

---

## 十五、追踪与文档阻塞

### 15.1 交付追踪记录

每个完成任务至少保留以下可定位证据：代码提交或合并请求、迁移 revision、自动化测试/评测报告、契约差异（如适用）以及 `CHECK-NNN-*` 的结论。证据只记录链接或路径，不在本文复制运行日志。

### 15.2 文档阻塞项模板

发现源文档冲突或缺失时，在实施记录中使用：

```text
BLOCK-DOC-NNN
关联任务：TASK-NNN
冲突来源：文件 + 章节
无法确定的语义：...
影响：...
处理：暂停相关实现 → 修正文档 → 评审通过 → 恢复任务
```

文档阻塞只暂停受影响任务；不受冲突影响且依赖已经满足的任务可以继续。
