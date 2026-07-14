# AI 工作流与领域命令

## 一、AI 边界

模型负责理解、归纳和提出规划建议；后端负责权限、版本、容量、引用、日期、事务和最终状态。

模型永远不能：

- 输出 SQL、JSON Patch 或数据库字段路径；
- 生成或猜测数据库 ID；
- 决定自身命令的最终权限；
- 绕过用户确认；
- 修改 advanced/closed Milestone；
- 修改已完成任务；
- 修改 UserWeekCapacity 或 UserWeekAllocation；
- 直接执行代码、访问任意网络或调用未授权工具。

---

## 二、模型引用与快照

### 2.1 稳定别名

PlanningSnapshot 对模型暴露稳定别名，不暴露数据库 ID：

```json
{
  "refs": {
    "project.current": {
      "name": "考研数学",
      "goal_type": "deadline"
    },
    "milestone.current": {
      "title": "积分基础",
      "status": "active"
    },
    "milestone.next": {
      "title": "积分综合应用",
      "status": "planned"
    },
    "week.active": {
      "week_start": "2026-07-13",
      "budget_minutes": 420
    },
    "task.1": {
      "title": "复习定积分基本性质",
      "status": "planned",
      "version": 3
    }
  }
}
```

后端单独保存 `ref → entity_type + database_id + version` 映射。命令校验时使用该映射，模型不能通过文本引用其他用户或快照外对象。

### 2.2 Snapshot 顶层结构

```json
{
  "schema_version": "planning-snapshot.v1",
  "workflow_type": "weekly_review",
  "business_date": "2026-07-13",
  "timezone": "Asia/Shanghai",
  "input_versions": {
    "route_revision": 8,
    "plan_revision": 15,
    "preference_revision": 4,
    "allocation_revision": 6,
    "task_event_revision": 10932
  },
  "user_capacity": {},
  "project_brief": {},
  "route_window": {},
  "active_week": {},
  "prepared_week": {},
  "recent_execution": {},
  "relevant_feedback": [],
  "material_summaries": [],
  "refs": {}
}
```

`prepared_week` 通常必有；任意 Project.target_date 落在当前执行周的 terminal deadline-week 项目允许为 null，并在 Snapshot 中显式写 `terminal_window=true`，禁止模型创建或延期任务到项目截止后。event_exclusive 与 date_inclusive 只决定截止当天是否可执行。

快照创建后不可修改。超出上下文预算时按以下顺序压缩：

1. 删除不相关历史消息；
2. 保留最近 2—3 条结构化 ProjectWeekAssessment，更早历史压成背景摘要；
3. 只保留当前、下一和少量受影响未来里程碑；
4. 使用材料摘要替代正文；
5. 若关键信息仍无法容纳，工作流返回 `need_input` 或拆分材料处理，不能静默截断关键规则。

### 2.3 证据引用

模型只能引用快照中存在的 evidence ref，例如：

- `task_event.10291`；
- `feedback.2`；
- `trend.last_4_weeks`；
- `material_summary.1`；
- `milestone.current`。

不存在的证据引用导致命令校验失败。

---

## 三、模型响应 Envelope

```json
{
  "schema_version": "planning-proposal.v1",
  "outcome": "changes",
  "summary": "本周积分基础推进正常，建议进入综合应用并保留一次基础复习。",
  "evidence_summary": [
    "主要任务已处理",
    "用户明确表示可以进入下一部分"
  ],
  "confidence": "medium",
  "questions": [],
  "commands": []
}
```

`outcome` 仅允许：

- `changes`：包含一个或多个命令；
- `no_changes`：命令为空；
- `need_input`：命令为空，questions 至少一项；
- `risk_detected`：命令可为空，必须给出风险说明和需要用户选择的问题。

顶层和所有命令均设置 `additionalProperties: false`。未知字段导致整个模型响应进入修复流程，不直接忽略。

---

## 四、命令公共结构

```json
{
  "command_id": "cmd_01",
  "command_type": "ResizeTask",
  "target_ref": "task.1",
  "expected_state": {
    "status": "planned",
    "version": 3
  },
  "payload": {
    "estimated_minutes": 30
  },
  "reason": "当前任务规模超过用户单次时长偏好",
  "evidence_refs": ["feedback.2", "task_event.10291"],
  "input_versions": {
    "plan_revision": 15,
    "allocation_revision": 6,
    "task_event_revision": 10932
  },
  "suggested_permission": "auto"
}
```

公共约束：

- `command_id`：响应内唯一，格式 `cmd_[a-zA-Z0-9_-]{1,40}`；
- `command_type`：白名单枚举；
- `target_ref`：必须存在于当前 Snapshot，或引用同一 Proposal 中更早创建的 temp_ref；创建命令可以为空或指向父对象；
- `expected_state`：包含命令真正依赖的旧值；
- `payload`：由 command_type 决定，未知字段拒绝；
- `reason`：1—500 字；
- `evidence_refs`：至少一项，且必须存在；
- `input_versions`：按命令依赖声明；
- `suggested_permission`：`auto / confirm / discuss`，只允许后端提升权限。

模型不输出 `idempotency_key`。后端在完成别名映射与 payload 规范化后计算：

```text
SHA256(planning_run_id + command_id + canonical_command_json)
```

---

## 五、白名单领域命令

### 5.1 初始规划专用命令

初始规划只在 Project.status=planning 时允许：

#### `CreateStage`

```json
{
  "temp_ref": "stage.foundation",
  "order_key": 10,
  "title": "基础重建",
  "objective": "覆盖核心基础内容",
  "strategy": {},
  "estimated_minutes": 1200,
  "target_start_week": "2026-07-13",
  "target_end_week": "2026-08-10"
}
```

#### `CreateMilestone`

```json
{
  "temp_ref": "milestone.integral_basic",
  "stage_ref": "stage.foundation",
  "order_key": 10,
  "title": "积分基础",
  "objective": "推进到可以开始综合应用的位置",
  "coverage": [],
  "progression_references": [],
  "estimated_minutes": 360,
  "target_week_start": "2026-07-27",
  "hard_prerequisites": []
}
```

#### `CreateWeekPlan`

```json
{
  "week_start": "2026-07-13",
  "summary": "建立基础并收集真实耗时",
  "task_command_refs": ["cmd_task_1", "cmd_task_2"]
}
```

这些命令必须作为一个初始规划原子批次应用。temp_ref 只在 Proposal 内有效，由后端创建真实 ID 并维护映射。

`CreateWeekPlan` 仅用于用户确认后原子应用 InitialPlanning 的当前周/下一周初始窗口。WeeklyReview、EventDrivenReplanning 和恢复流程不得提出该命令；这些流程使用容量分配事务已经确定性创建并绑定 allocation item 的 `week.prepared` 壳计划。

命令间引用形成有向无环图。后端验证所有 temp_ref 唯一、引用存在且不存在循环，再按 `CreateStage → CreateMilestone → CreateWeekPlan → CreateTask` 拓扑顺序应用。模型输出顺序不能替代依赖校验。

### 5.2 任务命令

#### `CreateTask`

目标：`week.active` 或 `week.prepared`。

payload：

```json
{
  "source_milestone_ref": "milestone.current",
  "title": "复习定积分基本性质",
  "description": "整理定义与常见性质",
  "estimated_minutes": 30,
  "necessity": "required",
  "prerequisite_refs": []
}
```

AI 只输出内容、预计分钟、`required/optional`、来源里程碑和可选硬前置引用。task_kind 由命令类型确定；week、user、project、due_date、order_key 和阻塞状态由上下文与后端生成。后端校验时长大于 0、来源同项目、依赖存在且无环、项目预算、用户周容量以及截止前 required 累计量。不存在每日或每周任务数量业务上限，只有模型响应技术安全上限。

#### `CreateReviewTask`

与 CreateTask 相同，但 `task_kind` 固定为 `review` 或 `remediation`，必须提供 `source_task_ref` 或 advanced/closed `source_milestone_ref`。

#### `ResizeTask`

payload：`{"estimated_minutes": 30}`。

只允许 planned Task。减少时长通常自动；增加时长需要重新检查预算，超过原时长 20% 或导致项目周总量明显变化时至少 confirm。

#### `DeferTask`

```json
{
  "target_week_ref": "week.prepared",
  "reason_code": "temporary_capacity",
  "replacement": {
    "estimated_minutes": 30,
    "necessity": "required"
  }
}
```

只允许 planned Task，目标必须是后续 prepared WeekPlan。应用时旧任务写 deferred 事件并进入终态，在目标周创建带 origin_task_id 的新任务；不能把旧行跨周移动。延期 optional 或用户已明确要求时可自动，required/关键任务延期至少 confirm，并重新校验截止可行性和依赖。若旧任务仍有未完成 dependent，必须在同一原子批次中明确完成、延期、替换或取消这些 dependent，或把依赖安全重绑到新任务；不允许留下指向终态 deferred 前置任务的悬空阻塞。

#### `CancelTask`

payload：

```json
{
  "reason_code": "duplicate",
  "replacement_command_ref": null
}
```

`reason_code`：`duplicate / obsolete / low_value / replaced / user_request`。已完成任务不能取消。取消关键任务至少 confirm。

### 5.3 里程碑命令

#### `KeepMilestone`

目标必须是 `milestone.current`。payload 可包含下一周策略：

```json
{
  "strategy": "continue",
  "focus": ["定积分基本性质"],
  "load_adjustment": "keep"
}
```

该命令不修改路线状态，但记录周评估决策，并作为生成 WeekPlan 的依据。

#### `AdvanceMilestone`

```json
{
  "next_milestone_ref": "milestone.next",
  "leftover_policy": "convert_to_review_tasks",
  "review_command_refs": ["cmd_review_1"]
}
```

校验：

- target_ref 是当前 active Milestone；
- next ref 是同项目 planned Milestone；
- 硬前置条件已客观满足；
- 遗留内容已被明确转换或取消；
- 用户在本次 Snapshot 中明确表示可以前进时可按既定权限自动应用；没有明确反馈时至少 confirm；
- advanced 状态不允许回退。

应用语义：如果 next_milestone 与当前节点同 Stage，只原子推进两个 Milestone；如果当前节点是当前 Stage 最后一个节点，则后端忽略模型对 Stage 状态的任何暗示，按领域规则原子冻结当前 Stage、激活下一 Stage 及其首个 Milestone，并只递增一次 route_revision。任一步失败时整个 Proposal 批次回滚。

#### `ShiftFutureMilestone`

```json
{
  "target_week_start": "2026-08-10"
}
```

只允许 planned/paused Milestone。修改目标周至少 confirm；不得修改 advanced/closed Milestone。

#### `ReshapeFutureMilestone`

```json
{
  "operation": "split",
  "supersede_refs": ["milestone.future_1"],
  "new_milestones": [
    {
      "temp_ref": "milestone.future_1a",
      "insert_after_ref": "milestone.current",
      "title": "积分计算强化",
      "objective": "...",
      "coverage": [],
      "progression_references": [],
      "estimated_minutes": 240,
      "target_week_start": "2026-08-03"
    }
  ]
}
```

operation 仅允许 `split / merge / replace / reorder`。只作用于尚未开始的 Milestone，必须 confirm；如果跨 Stage 改变主路径，升级为 discuss，不能自动应用。

---

## 六、模型不能直接提出的目标级变更

以下变化不作为模型领域命令输出：

- 修改最终目标；
- 修改截止日期；
- 暂停或结束项目；
- 修改用户长期容量；
- 改变多项目优先级；
- 重建 Stage 主路径。

模型应返回 `outcome=risk_detected` 或 `need_input`，给出问题和选项。用户明确选择后，由后端用户操作接口生成系统命令并记录 ProposalDecision。

---

## 七、权限矩阵

| 命令 | 自动执行条件 | 至少确认 | 必须讨论 |
|---|---|---|---|
| CreateTask | prepared 周内、预算内、非关键变化 | active 周新增或显著增量 | 无 |
| CreateReviewTask | 预算内轻量巩固 | 占用明显容量 | 无 |
| ResizeTask | 减量或不超过 20% 的小幅变化 | 增量超过 20% | 引发长期容量变化 |
| DeferTask | optional 或用户明确要求且截止安全 | required/关键任务跨周延期 | 影响截止策略或目标可达性 |
| CancelTask | 明显重复的 AI 任务 | 有价值或关键任务 | 改变目标范围 |
| KeepMilestone | 默认 | 明显改变负荷 | 无 |
| AdvanceMilestone | 用户在当前上下文明确同意且无硬前置阻塞 | 其他情况 | 改变 Stage 路径 |
| ShiftFutureMilestone | 无 | 普通目标周变化 | 影响最终截止 |
| ReshapeFutureMilestone | 无 | 同 Stage 内未来节点 | 跨 Stage 或改变主路径 |

后端 computed_permission 可以从 auto 提升到 confirm/discuss，不能降低产品规则要求。

---

## 八、工作流定义

### 8.1 GoalUnderstanding

- 触发：用户首次描述目标或目标修正对话；
- 输入：用户原文、材料摘要、现有用户容量与项目概览；
- 输出：结构化目标理解、缺失信息、目标类型、风险；
- 截止语义：只记录 target_date；考试/比赛默认 event_exclusive，交付默认 date_inclusive，无法判断时最多追问一次；
- 过期保护：target_date 已早于当前业务日期时不能进入 InitialPlanning，必须先确认新日期；
- 命令：无；
- 终止：信息足够进入 InitialPlanning，或返回最多一个关键问题。

### 8.2 InitialPlanning

- 触发：用户确认目标级信息；
- 输入：目标、容量分配、当前基础、材料摘要；
- 输出：CreateStage、CreateMilestone、CreateWeekPlan、CreateTask；
- 约束：只生成当前残周/执行周和下一预备周任务；
- 权限：整个初始批次由用户确认后应用。

### 8.3 WeeklyReview

- 触发：UserWeekRun 完成基线晋升和预算分配；
- 前置：容量协调事务已提交下一周 AllocationSet，并为下一周仍可执行的项目创建或复用绑定 allocation item 的空 `week.prepared`；若任意 Project.target_date 落在当前周，进入 terminal deadline-week 分支，不要求 prepared；
- 输入：当前主里程碑、上一周结果、最近 2—3 条 ProjectWeekAssessment、安全执行基线，以及可选的下一周 allocation item/`week.prepared`；
- 允许命令：任务命令、Keep/AdvanceMilestone、ShiftFutureMilestone；
- 禁止：CreateWeekPlan；
- terminal deadline-week：只允许调整 active 周截止前任务和暴露截止风险，不创建或延期任务到项目截止后；event_exclusive 不使用截止日，date_inclusive 可使用截止日；
- 截止风险：若 remaining required minutes 已超过截止前剩余容量，立即转入 EventDrivenReplanning，不等待趋势窗口；
- 禁止：目标级变化、跨 Stage 路线重建；
- 无信息时：KeepMilestone + 保守 prepared WeekPlan，或 need_input；
- 失败：保留安全基线并重试。

### 8.4 EventDrivenReplanning

- 触发：生病、出差、紧急目标、截止变化或明确硬阻塞等不能等待正常周滚动的重大事件；
- 第一步：判断影响是 project scope 还是 user scope；user scope 先由确定性协调器重算 UserWeekCapacity、创建新 AllocationSet 并重新绑定受影响 WeekPlan；
- 输入：相关 UserFeedback、执行周和预备周、最新 AllocationSet、当前里程碑、截止风险及最近 2—3 条 ProjectWeekAssessment；
- 允许命令：ResizeTask、DeferTask、CancelTask、CreateTask、CreateReviewTask；
- 输出影响性质：`temporary / observe / structural / goal_change`；
- temporary：只调整两周窗口；observe：调整近期并写 ProjectWeekAssessment；structural：创建 RemainingRouteCalibration；goal_change：返回 risk_detected，等待目标级确认；
- deadline_risk：无论过去 2—3 周趋势如何都必须即时处理；允许讨论缩减范围、增加容量或修改日期，未确认目标变化时不得把任务安排到 target_date 之后；
- 约束：不能直接修改 UserWeekCapacity/Allocation、目标、截止、Stage 主路径或历史 advanced/closed 对象。

### 8.5 RemainingRouteCalibration

- 触发：确认存在连续结构性偏差；
- 输入：冻结历史摘要、当前里程碑、剩余路线、容量与截止风险；
- 允许命令：ShiftFutureMilestone、ReshapeFutureMilestone、相关任务命令；
- 约束：只修改当前点之后；
- 权限：至少 confirm，跨 Stage 必须 discuss。

### 8.6 DeadlineClosure

- 类型：确定性领域流程，不调用模型；
- 触发：上海业务日期超过 planning/active/paused Project.target_date；
- 锁与校验：锁定 Project 并重读状态、target_date、deadline_day_policy 与 revision，重复扫描幂等返回既有快照；
- 原子效果：Project 转 closed，terminal_reason=deadline_reached；planned Task 写 cancelled + project_deadline_reached；未 advanced 路线转 closed；创建 ProjectClosureSnapshot；递增 route_revision/plan_revision；取消未终结 PlanningRun；失效未应用 Proposal；停止后续 WeekPlan；
- 输出：已完成/未完成内容、投入汇总、最后可行性状态和风险预警证据；
- 后续：closed 项目不可重开。用户选择继续时创建带 predecessor_project_id 的新 draft Project，由 GoalUnderstanding 重新判断旧未完成内容是否仍有价值。

### 8.7 FeedbackUnderstanding

- 触发：自然语言反馈；
- 输出：candidate_scope、impact_scope(project/user)、impact_nature(temporary/observe/structural/goal_change)、结构化候选值、置信度、是否需确认；
- 命令：无；
- 规则：goal_change 无论置信度多高都不能自动生效。

### 8.8 MaterialUnderstanding

- 前提：scan_status=clean；
- 输入：受限大小的已提取文本块；
- 输出：目录、摘要、与项目相关的信息和引用位置；
- 命令：无；
- 安全：材料指令视为数据，不得改变系统规则或调用工具。

---

## 九、验证流水线

```text
供应商 JSON 模式输出
→ JSON 解析
→ JSON Schema / Pydantic 校验
→ 别名解析
→ temp_ref 依赖图与循环校验
→ 证据引用校验
→ expected_state 校验
→ revision / task_event_revision 校验
→ 周总量、截止前累计容量与 date-only 语义预检
→ TaskDependency 引用与无环校验
→ 冻结对象保护
→ 权限计算与拆批
→ ProposalSet 与原子 Proposal 批次持久化
→ 自动应用或等待确认
```

失败分类：

- JSON/Schema 失败：最多一次格式修复调用；
- 引用或证据不存在：不修复为猜测 ID，整批 invalidated；
- 周总量或 `DEADLINE_CAPACITY_EXCEEDED`：返回 cutoff、available/required/overflow_minutes，可进行一次带明确错误反馈的重新规划；仍不可行则输出 risk_detected；
- 权限升级：不重试模型，后端直接改为 confirm/discuss；
- revision 冲突：检查命令依赖，相关命令失效并按需重新生成；
- 供应商失败：按 PlanningRun 重试策略处理。

每个工作流最多允许一次“生成 → 规则反馈 → 修正”。禁止无上限自我循环。

---

## 十、提示词版本与评测

- prompt_version 格式：`workflow_name.major.minor`；
- JSON Schema 不兼容变化提升 major；
- 文案或示例变化提升 minor；
- PlanningRun 记录 prompt_version、snapshot schema 和 command schema；
- 新版本先在离线评测集运行，再进入 staging；
- 生产灰度按用户哈希稳定分桶，不能同一用户同一周随机切换提示词；
- 评测比较约束遵守率、无效命令率、确认率、容量超限率和用户拒绝率，不只比较自然语言质量。
