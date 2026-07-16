# 后端与 AI 实施检查清单

本文是 `05-backend-ai-tasks.md` 的验收伴侣。每个 `CHECK-NNN-*` 只验证 `TASK-NNN`；任务只有在本节全部检查项通过且证据可定位后才能完成。

## 一、执行与证据规则

- 状态仅使用 `[ ]` 未检查、`[x]` 通过；失败项保持 `[ ]` 并关联缺陷，不用口头结论代替证据。
- 检查必须在与 CI 一致的固定依赖版本上执行；时间测试注入 Clock，AI 常规测试使用假 ModelGateway。
- 证据至少包含测试/流水线运行标识和可定位的报告、日志、迁移、OpenAPI 或指标路径；日志必须脱敏。
- 涉及并发时至少重复运行并保留随机种子/并发参数；一次偶然通过不构成验收。
- 若检查暴露源设计冲突，登记 `BLOCK-DOC-NNN`，先修正文档再修改期望结果。

## 二、TASK-001 工程骨架、依赖与本地环境

### CHECK-001-A 正常：干净环境启动

- [ ] **前置条件**：仅安装 Docker 和项目声明的开发工具，无已存在数据库卷或本地密钥。
- **检查步骤**：按 README 启动 PostgreSQL/Redis，安装锁定依赖，执行 Alembic、测试入口并启动 API。
- **预期结果**：依赖安装可重复；迁移成功；API 健康检查通过；测试发现 unit/integration/contract/evaluation/e2e 五层目录。
- **证据要求**：依赖锁文件、启动/迁移日志、健康检查响应和测试收集报告。

### CHECK-001-B 边界：模块依赖违规

- [ ] **前置条件**：架构依赖检查已接入测试或 CI。
- **检查步骤**：在隔离测试样例中令 domain 导入 FastAPI、Celery、ORM model 或供应商 SDK。
- **预期结果**：检查稳定失败并指出违规模块；移除违规引用后恢复通过。
- **证据要求**：失败与恢复两次检查报告。

## 三、TASK-002 配置、Clock、错误模型与可观测性基座

### CHECK-002-A 正常：时间与错误协议

- [ ] **前置条件**：可注入 Clock 和异常映射已启用。
- **检查步骤**：冻结上海时区的周日/周一、跨月和跨年时刻；分别触发成功请求与已知业务异常。
- **预期结果**：业务周/date 按上海时间计算，持久化 timestamp 为 UTC；错误含稳定 code、retryable、correlation_id 和安全 details。
- **证据要求**：时间单元测试、API 契约测试和关联日志样例。

### CHECK-002-B 失败：配置缺失与敏感信息

- [ ] **前置条件**：准备缺少数据库/签名关键配置的环境及包含敏感值的模拟异常。
- **检查步骤**：启动应用并触发异常响应/日志记录。
- **预期结果**：缺少关键配置时启动失败；客户端响应和结构化日志不含密钥、token、内部堆栈或其他用户数据。
- **证据要求**：启动失败日志和脱敏扫描结果。

## 四、TASK-003 用户、身份、设备会话与令牌轮换

### CHECK-003-A 正常：登录、轮换和按设备撤销

- [ ] **前置条件**：假微信 provider、迁移和认证接口可用。
- **检查步骤**：新用户登录，连续刷新，创建第二设备会话，撤销第一设备并校验两端 token。
- **预期结果**：User 与 provider identity 分离；refresh 仅存哈希且形成轮换链；第一设备失效，第二设备不受影响。
- **证据要求**：API 集成测试、脱敏数据库断言和令牌版本断言。

### CHECK-003-B 失败：旧 refresh token 重放

- [ ] **前置条件**：一个 refresh token 已成功轮换。
- **检查步骤**：再次提交旧 token，然后尝试使用该会话所有未过期 token。
- **预期结果**：重放被拒绝，整个会话及其未过期 refresh token 被撤销；其他设备会话不受影响。
- **证据要求**：重放集成测试和会话/token 状态断言。

### CHECK-003-C 竞争：同 token 并发刷新

- [ ] **前置条件**：同一有效 refresh token，至少两个并发请求。
- **检查步骤**：同时刷新并重复运行竞争测试。
- **预期结果**：最多一个请求完成正常轮换；其余按重放策略处理，不出现两个有效后继 token。
- **证据要求**：并发测试参数、数据库唯一性断言和运行报告。

## 五、TASK-004 用户偏好、API 幂等基座与租户保护

### CHECK-004-A 正常：偏好 revision 与幂等重放

- [ ] **前置条件**：两个用户、偏好记录和幂等存储可用。
- **检查步骤**：使用正确 revision 更新偏好；以相同用户/key/body 重试一个写请求。
- **预期结果**：revision 递增一次；重试返回首次响应且领域事务只执行一次；另一用户可复用同名 key。
- **证据要求**：API 测试、幂等记录和副作用计数断言。

### CHECK-004-B 失败：key 复用与租户越权

- [ ] **前置条件**：用户 A 已使用幂等 key，用户 B 拥有独立资源。
- **检查步骤**：A 用相同 key 提交不同 body；A 尝试读写 B 的资源并伪造外键。
- **预期结果**：分别返回 `IDEMPOTENCY_KEY_REUSED` 和 forbidden/not found；数据库复合外键拒绝绕过应用层的错误关联。
- **证据要求**：API/数据库集成测试和错误码断言。

### CHECK-004-C 竞争：偏好并发写

- [ ] **前置条件**：两个请求持有同一 preference revision。
- **检查步骤**：并发提交不同容量值。
- **预期结果**：仅一个成功，另一个返回 `PREFERENCE_REVISION_CONFLICT`，不存在静默覆盖。
- **证据要求**：并发测试及最终 revision/value 断言。

## 六、TASK-005 Project、Stage、Milestone 与关闭快照

### CHECK-005-A 正常：路线读模型

- [ ] **前置条件**：项目含冻结历史、一个 current 和多个未来节点。
- **检查步骤**：调用 route 和 closure 查询并核对排序、状态和 tentative 标记。
- **预期结果**：current/history/future 互斥；历史冻结、未来 tentative；终态项目仍可只读查询。
- **证据要求**：领域/契约测试和响应快照。

### CHECK-005-B 失败：唯一主节点与继任项目

- [ ] **前置条件**：已有主推进节点、其他用户项目及未 closed 项目。
- **检查步骤**：尝试创建第二主节点；分别以跨用户、非 closed 前项目创建继任项目。
- **预期结果**：数据库或领域约束拒绝全部非法操作，不产生半成品路线。
- **证据要求**：数据库约束测试和事务回滚断言。

## 七、TASK-006 项目状态机与确定性终态操作

### CHECK-006-A 正常：合法转换与完成

- [ ] **前置条件**：分别准备 draft、active、paused 项目。
- **检查步骤**：执行允许的规划激活、pause/resume、active complete 和 archive 路径。
- **预期结果**：状态、revision、terminal_reason 和 ended_at 正确；complete 记录 `user_completed`。
- **证据要求**：状态机单元测试和 API 集成测试。

### CHECK-006-B 失败：非法完成与 revision 冲突

- [ ] **前置条件**：paused/closed 项目及过期 project revision。
- **检查步骤**：调用 complete 或其他非法转换，并用旧 revision 修改项目。
- **预期结果**：返回 `STATE_TRANSITION_NOT_ALLOWED` 或 `PROJECT_REVISION_CONFLICT`；状态和副作用均不变化。
- **证据要求**：错误响应、事务前后数据库快照。

### CHECK-006-C 竞争：终态操作并发

- [ ] **前置条件**：一个 active 项目。
- **检查步骤**：并发提交 pause、complete 或 archive 中两个互斥操作。
- **预期结果**：只出现一个合法序列化结果，失败方无部分副作用。
- **证据要求**：并发集成测试和最终聚合状态断言。

## 八、TASK-007 用户周容量、分配版本与协调运行

### CHECK-007-A 正常：不可变分配版本

- [ ] **前置条件**：同用户同周有多个 active 项目和有限容量。
- **检查步骤**：创建首次 AllocationSet，再触发 reallocation。
- **预期结果**：新 set revision 追加，旧 set/item 不被覆盖；仅一个 active set；预算和不超过 allocatable minutes。
- **证据要求**：集成测试及新旧版本数据库断言。

### CHECK-007-B 边界：unfunded 与 paused

- [ ] **前置条件**：容量不足的低优先级 active 项目和 paused 项目。
- **检查步骤**：运行分配并查询用户周汇总。
- **预期结果**：低优先级项目得到 `unfunded/0/capacity_shortage` 且无 WeekPlan/PlanningRun；paused 不进入 allocation items。
- **证据要求**：策略单元测试、汇总响应和关联记录不存在断言。

### CHECK-007-C 竞争：并发重分配

- [ ] **前置条件**：同一 user/week 的多个 reallocation 请求。
- **检查步骤**：并发执行并重复压力循环。
- **预期结果**：不会产生两个 active set、重复 revision 或容量超配；失败运行可由 recovery 继续。
- **证据要求**：并发参数、唯一约束/汇总断言和死锁统计。

## 九、TASK-008 WeekPlan、Task、依赖与 TaskEvent 投影

### CHECK-008-A 正常：事件投影与累计耗时

- [ ] **前置条件**：一项 estimated=100 的 planned 任务。
- **检查步骤**：依次记录累计 40 分钟、完成、撤销/重开、延期，并查询任务/周汇总。
- **预期结果**：actual_minutes 始终按累计覆盖；reopened/deferred 不抹除旧周投入；延期新任务通过 origin 追踪剩余量。
- **证据要求**：状态机/集成测试和各步投影断言。

### CHECK-008-B 失败：依赖环与重复事件

- [ ] **前置条件**：三项任务和一个已成功事件请求。
- **检查步骤**：创建闭环硬依赖；重放相同幂等事件；用相同 key 提交不同 body。
- **预期结果**：依赖环返回 `TASK_DEPENDENCY_CYCLE`；同请求不重复递增；异体重放返回幂等 key 错误。
- **证据要求**：领域/接口测试及事件数量断言。

### CHECK-008-C 竞争：expected version 与事件水位

- [ ] **前置条件**：两个请求持有同一 task version。
- **检查步骤**：并发写不同 TaskEvent，并检查 Project.task_event_revision 与事件提交序。
- **预期结果**：仅一个成功；revision 无重复/跳过已提交事件；数据库 sequence 不参与水位判断。
- **证据要求**：并发测试、提交后事件/revision 查询。

## 十、TASK-009 容量、截止与周边界策略

### CHECK-009-A 正常：累计 cutoff 与部分投入

- [ ] **前置条件**：多项目、多 due date、部分 actual minutes 和 required/optional 任务样本。
- **检查步骤**：按每个 cutoff 运行预检并手工核对公式结果。
- **预期结果**：只累计 required；已有投入与剩余量不双计；所有项目共同占用截止前容量。
- **证据要求**：表驱动单元测试和公式输入/输出快照。

### CHECK-009-B 边界：日期策略和零可用日

- [ ] **前置条件**：event_exclusive、date_inclusive、当前周历史 due date、normal_days=0 样本。
- **检查步骤**：分别执行校验。
- **预期结果**：考试不计目标日、交付可计目标日；历史 due date 被拒绝；零可用日容量为 0 且不除零。
- **证据要求**：冻结时钟测试和规定错误码/details。

### CHECK-009-C 竞争：多 Proposal 共享容量

- [ ] **前置条件**：两个项目 Proposal 单独看均可行、合并后超出同一 cutoff 容量。
- **检查步骤**：并发预检并应用。
- **预期结果**：事务内复检保证最多一个成功，另一方得到容量冲突，最终汇总不超配。
- **证据要求**：并发数据库测试和最终容量断言。

## 十一、TASK-010 revision 向量、冻结保护与统一锁序

### CHECK-010-A 正常：相关 revision 精确失效

- [ ] **前置条件**：一个依赖 route 的命令、一个依赖 plan/task event 的命令。
- **检查步骤**：制造无关 TaskEvent、相关 TaskEvent 和路线变化，逐一应用命令。
- **预期结果**：无关事件不误杀；相关事件或 revision 变化返回对应冲突；只检查命令声明依赖。
- **证据要求**：领域/集成测试及 revision vector 断言。

### CHECK-010-B 失败：冻结和跨租户写

- [ ] **前置条件**：冻结 Milestone 和另一用户资源。
- **检查步骤**：尝试通过应用服务及直接仓储修改冻结节点或建立错误引用。
- **预期结果**：分别返回 `FROZEN_MILESTONE` 或被复合外键拒绝；事务回滚。
- **证据要求**：应用层与数据库层两组测试。

### CHECK-010-C 竞争：锁序与历史 allocation

- [ ] **前置条件**：并发 TaskEvent、Proposal、reallocation，含 settled/superseded 历史周。
- **检查步骤**：高频交叉执行并采集锁等待/死锁；补记历史周耗时。
- **预期结果**：统一锁序下无业务死锁/超配；历史汇总更新原绑定 allocation，不污染当前 active set。
- **证据要求**：压力参数、数据库锁统计和新旧 allocation 断言。

## 十二、TASK-011 核心资源 API、OpenAPI 与错误契约

### CHECK-011-A 正常：API 清单与契约

- [ ] **前置条件**：本期核心路由注册，OpenAPI 基线存在。
- **检查步骤**：运行 Auth/User、Project/Route、UserWeek/WeekPlan、Task/Event 契约测试并比较 OpenAPI。
- **预期结果**：路径、method、Schema、enum、分页、时间/date 和成功状态码符合详细设计；无未评审破坏性差异。
- **证据要求**：契约测试报告和 OpenAPI diff。

### CHECK-011-B 失败：写前置与安全错误

- [ ] **前置条件**：准备缺失 Idempotency-Key、旧 revision、非法字段和越权资源请求。
- **检查步骤**：调用各类写接口。
- **预期结果**：返回稳定校验/冲突/权限 code；业务分支不依赖 message；details 不泄密且无副作用。
- **证据要求**：错误响应快照和数据库前后断言。

## 十三、TASK-012 PlanningRun 轮询与 Proposal 决策 API

### CHECK-012-A 正常：异步轮询与接受决策

- [ ] **前置条件**：可控制状态推进的 PlanningRun 和待确认 Proposal。
- **检查步骤**：创建异步运行、轮询至终态，使用正确 expected status/versions 接受 Proposal。
- **预期结果**：创建返回 202/status URL/poll interval；终态停止建议轮询；决策仅应用一个原子批次。
- **证据要求**：契约/E2E 测试和状态序列记录。

### CHECK-012-B 失败：过期、失效和 GoalChange 冲突

- [ ] **前置条件**：过期 Proposal、依赖变化 Proposal 和旧 project/preference revision 的 GoalChange。
- **检查步骤**：提交决策/确认。
- **预期结果**：返回规定 expired/invalidated/revision code；无部分应用；GoalChange 拒绝路径只记录 Decision。
- **证据要求**：API 响应和命令/决策/业务表断言。

### CHECK-012-C 竞争：重复决策

- [ ] **前置条件**：一个 pending_confirmation Proposal。
- **检查步骤**：并发提交 accept/reject 或两个 accept。
- **预期结果**：只接受一个合法终结决策；重复幂等响应一致；不存在重复命令副作用。
- **证据要求**：并发测试和 Decision/Command 计数。

## 十四、TASK-013 PlanningRun、Outbox 与可靠投递

### CHECK-013-A 正常：事务提交到 Broker confirm

- [ ] **前置条件**：真实 PostgreSQL、测试 Broker/Redis 和 Dispatcher。
- **检查步骤**：在业务事务创建 Run/Outbox，提交后运行 Dispatcher 至 Broker confirm。
- **预期结果**：事务内不直接 publish；消息 pending→claimed→published；payload 仅含允许的 ID/路由元数据。
- **证据要求**：数据库状态序列、Broker 消息和 Dispatcher 日志。

### CHECK-013-B 失败：回滚、发布失败与 dead

- [ ] **前置条件**：可注入事务回滚和 Broker publish 失败。
- **检查步骤**：分别触发业务回滚、连续发布失败超过最大次数。
- **预期结果**：回滚不留下 Run/Outbox；发布失败按退避重试，最终 dead 并告警，不误标业务 succeeded。
- **证据要求**：故障注入报告、状态/attempt/next_retry 断言和告警事件。

### CHECK-013-C 竞争：多 Dispatcher 与 claim 过期

- [ ] **前置条件**：多个 Dispatcher、同一批消息和可暂停的 claimant。
- **检查步骤**：并发 claim，令一实例在 confirm 前超过 lease，再由其他实例领取。
- **预期结果**：同一时刻只有一名有效 claimant；重复发布通过业务幂等无重复副作用；published 不覆盖 running/succeeded。
- **证据要求**：并发日志、claim owner 序列和业务副作用计数。

## 十五、TASK-014 Worker lease、重试、恢复扫描与 Scheduler

### CHECK-014-A 正常：领取、心跳与终态

- [ ] **前置条件**：pending/queued/retry_wait 三类 Run 和 Worker。
- **检查步骤**：领取运行、续租并成功提交终态。
- **预期结果**：CAS 状态合法，heartbeat/lease 更新；只有当前 owner 写 succeeded；attempt 记录正确。
- **证据要求**：Worker 集成测试和状态时间线。

### CHECK-014-B 失败：硬杀、不可重试与 dead

- [ ] **前置条件**：可终止 Worker、控制错误类型和时间的测试环境。
- **检查步骤**：硬杀 running Worker；触发可重试直至上限及不可重试错误。
- **预期结果**：扫描器不依赖旧进程善后，分别转 retry_wait/dead/failed；旧 owner 恢复后无法提交。
- **证据要求**：故障注入日志、CAS 失败和最终状态断言。

### CHECK-014-C 竞争：重复扫描与旧 Worker

- [ ] **前置条件**：多个扫描器候选、过期 lease 和暂停后恢复的旧 Worker。
- **检查步骤**：并发扫描并让新 Worker 完成，再放行旧 Worker。
- **预期结果**：只创建一次幂等重投；新终态保留；旧结果被 fencing/CAS 拒绝。
- **证据要求**：并发运行报告、Outbox 数量和终态 owner 断言。

## 十六、TASK-015 Snapshot、稳定别名与证据引用

### CHECK-015-A 正常：最小上下文与版本记录

- [ ] **前置条件**：含路线、两周任务、三周评估和无关历史的项目。
- **检查步骤**：构建 Snapshot 并持久化/重建。
- **预期结果**：包含所需最小信息、稳定别名、revision/event 水位和版本；排除无关全量历史和真实数据库 ID。
- **证据要求**：Snapshot Schema 测试和脱敏快照样本。

### CHECK-015-B 失败：伪造、跨运行和过期引用

- [ ] **前置条件**：两个用户/运行的别名及旧 evidence ref。
- **检查步骤**：交叉解析别名并提交不存在或过期证据。
- **预期结果**：全部在命令生成/应用前拒绝，不泄露真实对象或其他用户存在性。
- **证据要求**：验证器测试和安全错误断言。

## 十七、TASK-016 ModelGateway、响应 Envelope 与验证流水线

### CHECK-016-A 正常：合法结构化输出

- [ ] **前置条件**：假 ModelGateway 和合法工作流样本。
- **检查步骤**：调用网关并依次经过全部验证阶段。
- **预期结果**：生成 validated 候选；记录模型/Prompt/Schema、token、费用、延迟；常规测试无网络访问。
- **证据要求**：离线测试、ModelInvocation 断言和网络禁用证明。

### CHECK-016-B 失败：非法/越权/超容量输出

- [ ] **前置条件**：缺字段、数据库 ID、假别名、JSON Patch、非白名单、低报权限、依赖环、超容量样本。
- **检查步骤**：逐样本运行验证流水线并记录停止阶段。
- **预期结果**：每个样本在业务落库前由对应阶段拒绝；模型建议不能降低后端权限。
- **证据要求**：表驱动测试和阶段/错误分类报告。

### CHECK-016-C 降级：模型超时和供应商故障

- [ ] **前置条件**：已有生效计划，可注入 timeout/429/5xx/Schema 永久错误。
- **检查步骤**：运行工作流并观察重试分类及业务读取。
- **预期结果**：可重试错误进入 retry，永久错误失败；已生效路线/任务不变且可读。
- **证据要求**：故障测试、PlanningRun 状态和业务表前后快照。

## 十八、TASK-017 ProposalSet、原子 Proposal、领域命令与权限拆批

### CHECK-017-A 正常：权限拆批与原子应用

- [ ] **前置条件**：一次响应含自动、确认和讨论级命令。
- **检查步骤**：构建 ProposalSet，应用自动批次，再生成/接受确认批次。
- **预期结果**：一个 Run 仅一个 Set；批次权限正确；待确认批次基于自动应用后的新版本；Decision 可审计。
- **证据要求**：领域/集成测试和 Set/Proposal/Command/Decision 图谱。

### CHECK-017-B 失败：批内任一命令失败

- [ ] **前置条件**：一个多命令 Proposal，其中末条违反前置或容量。
- **检查步骤**：提交应用并重试相同请求。
- **预期结果**：整个 Proposal 回滚，无前序命令残留；重试不产生副作用；状态/错误稳定。
- **证据要求**：事务前后快照和命令副作用计数。

### CHECK-017-C 竞争：Proposal 与 TaskEvent/reallocation

- [ ] **前置条件**：共享计划/容量的 Proposal、TaskEvent 和 reallocation。
- **检查步骤**：按不同交错并发执行。
- **预期结果**：锁后复检使过期一方失效；无超配、丢更新或部分 Decision。
- **证据要求**：并发矩阵、最终 revisions 和容量汇总。

## 十九、TASK-018 GoalUnderstanding 与 InitialPlanning 闭环

### CHECK-018-A 正常：首次规划后端闭环

- [ ] **前置条件**：新用户容量、假模型合法目标与规划输出。
- **检查步骤**：创建 draft、发起运行、轮询、确认并读取路线/用户周/任务。
- **预期结果**：先分配周容量，再原子创建路线/计划；项目 active；任务不越过 allocation；审计链完整。
- **证据要求**：后端 E2E 报告和 Project→Run→Set→Proposal→Decision→Plan 追踪记录。

### CHECK-018-B 失败：信息不足、容量不足与版本变化

- [ ] **前置条件**：缺失关键信息目标、竞争项目耗尽容量、确认前 revision 变化三组样本。
- **检查步骤**：分别运行并尝试确认。
- **预期结果**：信息不足请求澄清；容量不足缩减/unfunded/待确认，不抢占锁定预算；旧候选冲突且不部分落路线。
- **证据要求**：E2E 响应、容量和路线事务断言。

### CHECK-018-C 降级：模型失败后恢复

- [ ] **前置条件**：首次调用可重试失败，后续假模型成功。
- **检查步骤**：观察 Run 重试并最终完成。
- **预期结果**：同 generation 不重复建项目/ProposalSet；恢复后从可信状态继续。
- **证据要求**：Run/Outbox/Proposal 数量和状态时间线。

## 二十、TASK-019 周一安全基线与 AllocationSet 滚动

### CHECK-019-A 正常：确定性晋升与建壳

- [ ] **前置条件**：funded prepared、funded 缺壳、unfunded、paused、deadline-week、calibration-hold 项目混合用户。
- **检查步骤**：运行 rollover 并查询当前/下一周。
- **预期结果**：符合条件计划晋升；缺壳建空 baseline 并记 anomaly；下一周只为准入项目建壳/Outbox；其他分支无运行。
- **证据要求**：协调服务集成测试和各分支记录断言。

### CHECK-019-B 失败：AI 全部超时

- [ ] **前置条件**：安全基线已晋升，所有 WeeklyReview 模型调用超时。
- **检查步骤**：持续查询任务和用户周并记录任务事件。
- **预期结果**：已晋升计划可读可执行；不清空计划、不伪造替代数据；运行显示可重试/失败。
- **证据要求**：故障 E2E、业务表前后快照和 API 响应。

### CHECK-019-C 竞争：Scheduler 与 ensure-active

- [ ] **前置条件**：尚未晋升的同一 user/week。
- **检查步骤**：后台扫描和多个 ensure-active 请求并发触发。
- **预期结果**：只完成一次 promotion、一个 rollover run/幂等结果和一组下一周分配；无重复任务。
- **证据要求**：并发测试、唯一键与计数断言。

## 二十一、TASK-020 WeeklyReview、残周窗口与暂停重分配

### CHECK-020-A 正常：WeeklyReview 与延期

- [ ] **前置条件**：active 周、prepared 壳、未完成 planned 任务及有效预算。
- **检查步骤**：运行 WeeklyReview、周末结算并查询新周任务。
- **预期结果**：只修改既有窗口；旧任务 deferred；新任务带 origin 且仅规划剩余量；历史节点不变。
- **证据要求**：工作流/E2E 测试和任务链断言。

### CHECK-020-B 边界：两类残周窗口

- [ ] **前置条件**：冻结 Clock 至本周剩余分别不少于 4 天和少于 4 天。
- **检查步骤**：完成首次规划。
- **预期结果**：前者创建两周窗口；后者创建三周窗口且残周仅 1—2 个启动任务；每周绑定正确 allocation。
- **证据要求**：冻结时间 E2E 和 WeekPlan/allocation 图谱。

### CHECK-020-C 竞争：暂停与周滚动/Worker

- [ ] **前置条件**：项目有当前/未来计划、未锁定预算及运行中的 WeeklyReview。
- **检查步骤**：并发 pause、rollover 和 Worker 提交，再执行 resume 无预算/有预算分支。
- **预期结果**：序列化后 paused 释放预算、supersede/取消/失效完整；旧 Worker 不能写回；resume 仅获正预算后建壳。
- **证据要求**：并发状态图、分配版本及任务/Run/Proposal 断言。

## 二十二、TASK-021 Feedback、趋势评估与事件驱动重规划

### CHECK-021-A 正常：五类反馈路由

- [ ] **前置条件**：完成事实、当前阻塞、轻微困难、用户容量变化和目标变化样本。
- **检查步骤**：提交反馈、轮询分类并确认需要确认的候选。
- **预期结果**：依次路由 TaskEvent、temporary、observe、UserWeekRun reallocation、goal_change；普通事实不创建复杂运行。
- **证据要求**：表驱动工作流/E2E 测试和生成对象类型断言。

### CHECK-021-B 失败：模型分类与确定性规则冲突

- [ ] **前置条件**：假模型试图把目标/长期容量变化降级为可自动应用。
- **检查步骤**：执行 FeedbackUnderstanding 和权限校验。
- **预期结果**：确定性规则提升权限并要求用户确认；模型不能直接应用目标级变化。
- **证据要求**：分类/权限测试和 Proposal 状态断言。

### CHECK-021-C 竞争：用户级容量变化

- [ ] **前置条件**：一个反馈影响多个 active 项目。
- **检查步骤**：并发处理重复反馈及派生项目运行。
- **预期结果**：仅一个 UserWeekRun 创建新 AllocationSet，之后按项目预算派生运行；项目 Worker 不独立改容量。
- **证据要求**：运行拓扑、AllocationSet 数量和幂等键断言。

## 二十三、TASK-022 路线校准、GoalChange 与 DeadlineClosure

### CHECK-022-A 正常：趋势、校准和 GoalChange

- [ ] **前置条件**：连续评估样本、结构性信号和待确认 GoalChange。
- **检查步骤**：推进 2—3 周趋势，确认校准/GoalChange 并查询路线。
- **预期结果**：单次 observe 不误触发结构性调整；确认后只修改当前点之后路线；冻结历史保持不变。
- **证据要求**：趋势/工作流测试和路线前后快照。

### CHECK-022-B 边界：截止风险与确定性关闭

- [ ] **前置条件**：不可行但未到期项目、已过 target_date 的 active/paused 项目。
- **检查步骤**：运行每日扫描两次。
- **预期结果**：风险立即重规划；到期项目 closed 而非 completed，planned 任务取消、路线关闭、生成唯一 ClosureSnapshot，重复扫描幂等。
- **证据要求**：冻结时钟集成测试和关闭对象计数。

### CHECK-022-C 竞争：关闭与 Worker/Proposal

- [ ] **前置条件**：到期项目同时有 running Worker 和 pending_confirmation Proposal。
- **检查步骤**：并发执行 DeadlineClosure、Worker 终态和 Proposal accept。
- **预期结果**：DeadlineClosure 优先胜出；旧 Run 取消/终结、Proposal invalidated，任何旧命令不能在 closed 后应用。
- **证据要求**：并发时间线、CAS/revision 错误及最终项目图谱。

## 二十四、TASK-023 测试体系、AI 评测集与 CI 质量门

### CHECK-023-A 正常：十项 CI 门禁

- [ ] **前置条件**：完整 CI 配置和固定依赖版本。
- **检查步骤**：运行 Ruff/格式、类型、单元、PG/Redis 集成、Alembic 前进、OpenAPI、JSON Schema、安全/密钥、AI 评测、Docker 构建。
- **预期结果**：十项均自动执行且全部通过；结果可从任务追踪到报告。
- **证据要求**：一次完整成功流水线及各 job 报告链接。

### CHECK-023-B 失败：门禁确实阻止合并

- [ ] **前置条件**：隔离分支/测试样例可分别注入类型错误、破坏性契约、密钥和 AI 越权回归。
- **检查步骤**：逐类注入并运行对应 job。
- **预期结果**：每类问题都使流水线失败且定位明确；移除问题后恢复。
- **证据要求**：失败/恢复流水线记录。

### CHECK-023-C 可复现：离线 AI 评测

- [ ] **前置条件**：核心匿名评测集、固定 Prompt/Schema/配置和随机种子。
- **检查步骤**：在禁网环境重复运行两次。
- **预期结果**：覆盖规定案例，约束指标一致可复现；失败报告含版本和输入标识而非敏感正文。
- **证据要求**：两次评测报告和网络禁用配置。

## 二十五、TASK-024 可观测性、压测、迁移与发布基线

### CHECK-024-A 正常：端到端可观测性

- [ ] **前置条件**：指标、日志、追踪和告警环境可用。
- **检查步骤**：执行一次 API→Run→Outbox→Worker→ModelInvocation→Proposal 流程并注入一次 retry/dead。
- **预期结果**：correlation ID 可串联全链路；延迟、费用、重试、积压、dead、lease 和周滚动指标可查询；告警触发并可定位。
- **证据要求**：脱敏追踪样例、指标查询和告警事件。

### CHECK-024-B 容量：上线前压测基线

- [ ] **前置条件**：类生产 PostgreSQL/Redis/Worker 配置和压测数据生成器。
- **检查步骤**：验证 1 万用户×3 active 周一晋升、100 并发 Proposal、重复投递、多 Dispatcher、供应商限流积压恢复和模型超时 30 分钟。
- **预期结果**：无容量突破、重复副作用或不可恢复运行；锁等待/死锁/慢查询、队列清空时间和资源用量有测量值。
- **证据要求**：压测脚本版本、环境配置、原始结果和结论报告。

### CHECK-024-C 失败：降级、迁移和回滚

- [ ] **前置条件**：可演练的 staging、expand/contract 迁移和备份。
- **检查步骤**：滚动发布期间分别中断模型、Redis、Worker/外部平台；执行前进迁移、旧代码兼容验证和允许范围内回滚/恢复。
- **预期结果**：已生效路线/任务保持可读，允许的 TaskEvent 可写，恢复后幂等续跑；迁移不要求新旧代码同时瞬时切换；备份可恢复。
- **证据要求**：故障演练、迁移/回滚 Runbook 执行记录和恢复校验。

## 二十六、最终发布门

以下项目全部通过后，核心规划后端与 AI 才可进入生产发布审批：

- [ ] `CHECK-001-*` 至 `CHECK-024-*` 无未关闭项，且每项证据可定位。
- [ ] 所有 `BLOCK-DOC-*` 已通过权威技术文档修订关闭，不存在代码自行选择的冲突语义。
- [ ] Alembic 前进迁移、OpenAPI/JSON Schema 兼容性和 Docker 镜像构建均使用拟发布 commit 验证。
- [ ] AI 核心评测集达到已评审门槛，真实模型 staging 验证通过，生产仍保留确定性验证和安全降级。
- [ ] 上线容量结论来自 `CHECK-024-B` 实测，供应商配额、队列并发、成本预算和告警阈值已记录配置版本。
- [ ] 发布/回滚 Runbook、值班告警路径、数据库备份恢复与密钥配置完成演练。
- [ ] 客户端、材料和通知仍明确不在本期交付，不以未验证占位实现进入生产。
