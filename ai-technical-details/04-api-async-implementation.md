# API、异步协议与实施蓝图

## 一、API 通用约定

### 1.1 基础约定

- 前缀：`/api/v1`；
- 格式：JSON，UTF-8；
- 时间戳：ISO 8601 UTC，例如 `2026-07-13T08:30:00Z`；
- 业务日期：`YYYY-MM-DD`，固定解释为 `Asia/Shanghai`；
- ID：UUID 字符串；
- 分页：游标分页，`limit` 默认 20、最大 100；
- API 契约：FastAPI OpenAPI，CI 生成 TypeScript SDK；
- 客户端不得依据展示文案判断状态，只使用稳定 code 与 enum。

### 1.2 成功响应

单资源直接返回资源对象。创建异步任务返回 `202 Accepted`：

```json
{
  "run_id": "019...",
  "status": "pending",
  "status_url": "/api/v1/planning-runs/019...",
  "poll_after_ms": 1500
}
```

### 1.3 错误响应

```json
{
  "error": {
    "code": "PLAN_REVISION_CONFLICT",
    "message": "计划已发生变化，请刷新后重试",
    "retryable": false,
    "correlation_id": "req_019...",
    "details": {
      "expected": 15,
      "actual": 16
    }
  }
}
```

客户端显示 message；业务分支只使用 code。

### 1.4 幂等与并发

- 所有创建、确认和任务事件 POST 请求要求 `Idempotency-Key`；
- 服务端保存用户范围内的请求键、请求摘要和首次响应；
- 同一 key 使用不同请求体返回 `IDEMPOTENCY_KEY_REUSED`；
- `api_idempotency_records` 以 `(user_id, key)` 唯一保存规范化 method/path、request_hash、处理租约和首次完成响应；相同请求重试返回首次响应，不能重新执行领域事务；
- 修改偏好、项目和计划资源使用 `If-Match` 或请求体 revision；
- revision 冲突返回 HTTP 409，不自动覆盖。

### 1.5 认证

- 微信小程序用 `wx.login` code 换取内部 session；
- 后端保存微信 provider_subject 与内部 User 的绑定；
- access token 短期有效，refresh token 轮换；
- refresh token 只保存哈希，可按设备撤销；
- Web/App 后续增加 Identity Provider，不改变业务 User ID；
- 敏感操作校验用户状态与 token version。

---

## 二、API 清单

### 2.1 Auth 与 User

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/wechat/login` | 微信 code 登录或注册 |
| POST | `/auth/refresh` | 刷新并轮换 token |
| POST | `/auth/logout` | 撤销当前 refresh token |
| GET | `/auth/sessions` | 查询当前用户的有效设备会话 |
| DELETE | `/auth/sessions/{session_id}` | 按设备撤销指定会话及其 refresh token |
| POST | `/auth/logout-all` | 撤销全部会话并提升用户 token version |
| GET | `/me` | 当前用户与偏好 |
| PATCH | `/me/preferences` | 修改容量与稳定偏好，需 preference_revision |
| DELETE | `/me` | 发起账号删除流程 |

`PATCH /me/preferences` 中长期容量变化必须明确展示影响，并递增 preference_revision。

`POST /auth/refresh` 在同一事务中锁定 `AuthSession` 与当前 `RefreshToken`，将旧 token 标记为 `rotated`，创建只保存哈希的新 token，并建立轮换链。已使用 token 再次出现属于重放，必须撤销整个会话及其未过期 token。访问令牌同时携带并校验 `user_id`、`session_id`、`users.auth_version` 与 `auth_sessions.session_version`；按设备撤销只影响目标会话，全量退出提升 `users.auth_version`。

### 2.2 Projects 与 Route

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/projects` | 创建 draft 项目 |
| GET | `/projects` | 项目列表 |
| GET | `/projects/{project_id}` | 项目详情与当前版本 |
| GET | `/projects/{project_id}/closure` | 到期关闭后的不可变结算摘要 |
| PATCH | `/projects/{project_id}` | 修改允许直接编辑的名称等非目标字段 |
| POST | `/projects/{project_id}/initial-planning` | 发起 GoalUnderstanding/InitialPlanning |
| GET | `/projects/{project_id}/route` | 当前阶段、里程碑和未来路线 |
| POST | `/projects/{project_id}/pause` | 用户确认暂停 |
| POST | `/projects/{project_id}/resume` | 恢复项目 |
| POST | `/projects/{project_id}/complete` | 用户确认目标实际达成并结束项目 |
| POST | `/projects/{project_id}/archive` | 归档项目 |

目标、截止和优先级变化不通过普通 PATCH 静默修改，应先创建 UserFeedback/Proposal 或专用确认操作。

`GET /projects/{project_id}/route` 是路线数据的唯一读取接口。除当前路线外，它还返回冻结的历史里程碑和暂定未来里程碑；不返回未来具体任务，也不把里程碑状态解释为能力认证：

```json
{
  "project_id": "p_123",
  "route_revision": 9,
  "current": {
    "stage": {"id": "stage_2", "title": "强化应用"},
    "milestone": {"id": "milestone_4", "title": "综合练习", "status": "active"}
  },
  "history_milestones": [
    {
      "id": "milestone_3",
      "title": "基础概念",
      "stage_title": "基础建立",
      "status": "advanced",
      "transitioned_at": "2026-07-14T09:00:00+08:00"
    }
  ],
  "future_milestones": [
    {
      "id": "milestone_5",
      "title": "综合输出",
      "stage_title": "实践输出",
      "status": "planned",
      "target_week_start": "2026-08-10",
      "tentative": true
    }
  ]
}
```

`history_milestones` 只包含 `advanced / superseded / closed` 的冻结对象，按路线顺序返回。`future_milestones` 只包含尚未开始的 `planned / paused` 对象，按阶段和里程碑顺序返回，所有项固定 `tentative=true`。当前 Milestone 不得同时出现在两个列表；项目归档、关闭或完成后保留历史和路线快照的只读查询，但不返回可执行任务。接口只定义字段、顺序和状态语义，不规定客户端展示方式。

`POST /projects/{project_id}/pause` 在同一用户周重分配事务中完成：保留已完成任务和实际投入；取消当前与后续窗口中仍为 planned 的任务；将当前 active WeekPlan 和全部后续 prepared WeekPlan 置为 superseded；将当前 active allocation 与后续 reserved allocation 置为 released；取消项目规划运行并使未应用 Proposal 失效；随后仅以未锁定的剩余容量创建新的 AllocationSet 供其他 active 项目分配。paused 项目不占容量、不生成任务。`POST /projects/{project_id}/resume` 创建新的 AllocationSet 版本，项目只有重新获得大于 0 的预算后才创建 prepared 计划并投递 WeeklyReview。

`POST /projects/{project_id}/complete` 要求 `Idempotency-Key` 请求头，请求体为：

```json
{
  "expected_project_revision": 6,
  "completion_note": "已完成最终交付"
}
```

仅 active Project 可执行。事务重新校验 revision 后写 `status=completed`、`terminal_reason=user_completed`、`ended_at`，关闭未 advanced 路线、以 `reason_code=project_completed` 取消仍为 planned 的任务，将当前 active 和未来 prepared WeekPlan 全部置为 `superseded`，释放其未 settled allocation，取消未终结 PlanningRun 并失效未应用 Proposal。已 settled WeekPlan 保持只读历史。AI 和普通反馈分类不得自动调用本接口；到期但未确认达成仍走 DeadlineClosure → closed。

GoalChange 使用独立的 `/goal-changes/{candidate_id}/confirm`，不复用 `/feedback/{feedback_id}/confirm` 直接应用；但不建立独立持久化表。`candidate_id` 就是 `proposal_kind=system_goal_change/system_preference_change` 的 PlanningProposal.id，查询、过期、拒绝、失效和决策审计复用 Proposal/ProposalDecision。请求必须通过 `Idempotency-Key` 请求头提供幂等键；请求体只包含后端生成的候选 ID、确认结果和版本：

```json
{
  "candidate_id": "gc_123",
  "decision": "accept",
  "expected_project_revision": 6,
  "expected_preference_revision": 4
}
```

示例请求头：`Idempotency-Key: goal-change-confirm-01`。不接受请求体中的 `idempotency_key`；缺失请求头、同一用户重复使用不同请求体或规范化请求摘要不一致时，分别按通用约定返回校验错误或 `IDEMPOTENCY_KEY_REUSED`。

服务端根据 candidate_id 读取已保存的影响预览，重新校验 `expected_project_revision`（项目变更）或 `expected_preference_revision`（长期容量/偏好变更），通过后才执行 `ApplyProjectGoalChange`/`ApplyPreferenceChange`。成功响应示例：

```json
{
  "candidate_id": "gc_123",
  "decision": "accepted",
  "project_id": "p_123",
  "project_revision": 7,
  "route_revision": 9,
  "plan_revision": 17,
  "planning_run_id": "run_456"
}
```

拒绝只记录 `decision=rejected`，不改变项目。版本冲突返回 `409 PROJECT_REVISION_CONFLICT` 或 `409 PREFERENCE_REVISION_CONFLICT`，并包含 `candidate_id`、`expected_revision`、`current_revision` 和 `requires_refresh=true`；客户端必须重新获取候选，不能强制覆盖。

创建继任项目仍使用 POST `/projects`，可带 predecessor_project_id；后端只允许引用同一用户且 status=closed 的项目。旧任务不会自动复制，新项目必须重新经过 GoalUnderstanding/InitialPlanning。

截止只接受 `YYYY-MM-DD`。GoalUnderstanding 将考试/比赛规范化为 `deadline_day_policy=event_exclusive`，交付规范化为 `date_inclusive`；无法判断时只追问是否可在截止当天执行，不接收具体时刻。

周中确认新项目的初始计划时，应用服务按上海业务日期计算残周：剩余不少于 4 天时，为当前周和下一周创建或复用 UserWeekCapacity；剩余少于 4 天时，额外创建或复用下下周容量，以支持“残周启动 + 下一执行周 + 后一预备周”。应用服务为每个受影响周创建 `run_type=reallocation` 的 UserWeekRun，只重新分配尚未锁定预算，不重复执行周一基线晋升。

### 2.3 User Week 与 WeekPlan

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/user-weeks/current` | 当前用户周容量、各项目预算和汇总 |
| GET | `/user-weeks/{week_start}` | 指定周汇总 |
| GET | `/projects/{project_id}/weeks/current` | 项目执行周与预备周 |
| GET | `/projects/{project_id}/weeks/{week_start}` | 指定项目周计划 |
| POST | `/user-weeks/current/ensure-active` | 幂等确保周一安全基线，供首次打开兜底 |

`ensure-active` 仅创建或复用 `run_type=rollover` 的 UserWeekRun 并执行确定性晋升，不同步调用模型。后台 Scheduler 与该接口共享同一 rollover 幂等键。

### 2.4 Tasks 与 TaskEvent

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/tasks/current-week` | 本周任务池，返回必要性、推荐顺序、可选截止和派生阻塞状态 |
| GET | `/tasks` | 按周、项目、状态、必要性和截止日期查询 |
| GET | `/tasks/{task_id}` | 任务详情 |
| POST | `/tasks/{task_id}/events` | 完成、撤销、跳过、恢复跳过、记录耗时 |

事件请求：

```json
{
  "event_type": "completed",
  "expected_task_version": 3,
  "actual_minutes": 28,
  "note": null,
  "occurred_at": "2026-07-13T08:30:00Z"
}
```

服务端在同一事务中更新 Task 当前状态、递增 version 并追加 TaskEvent。`actual_minutes` 表示该任务截至本次事件的累计总投入；完成事件与 duration_recorded 事件都覆盖同一 Task.actual_minutes 投影，不能把两条事件相加。重复请求由 `Idempotency-Key` 请求头去重；已记录的投入在 reopened 或 deferred 后仍归属于原周。

`GET /tasks/current-week` 返回完整周任务池，不设置业务数量上限。按 `necessity desc, order_key` 排序，并为每项派生 `is_blocked` 与未满足 prerequisite 摘要。服务端不能以截断隐藏任务；只通过分页保护接口。不存在用户直接创建 Task 的 POST，新增行动必须先进入 Feedback/Conversation 和规划命令校验。

`GET /user-weeks/current` 和项目周汇总必须返回 `allocation.status=unfunded`、`budget_minutes=0`、`allocation_reason=capacity_shortage`，展示“本周未排入容量”；该状态没有 WeekPlan、任务或 PlanningRun，不返回“计划正在生成”。

### 2.5 Feedback 与 Conversation

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/feedback` | 保存自然语言反馈并返回分类运行 ID |
| GET | `/feedback/{feedback_id}` | 查询候选分类和处理状态 |
| POST | `/feedback/{feedback_id}/confirm` | 确认反馈分类；目标级变更只生成待确认候选，不直接应用 |
| GET | `/goal-changes/{candidate_id}` | 获取 GoalChange 候选、影响预览和 expected revisions |
| POST | `/goal-changes/{candidate_id}/confirm` | 接受或拒绝 GoalChange；接受后应用系统命令 |
| GET | `/projects/{project_id}/conversations` | 对话列表 |
| POST | `/projects/{project_id}/messages` | 发送消息并创建必要工作流 |

消息接口返回已保存 Message 和可选 PlanningRun。保存消息成功不等于 AI 回复成功。

重大反馈分类结果必须包含 impact_scope、impact_nature、urgency 和 execution_blocked。impact_scope=user 时，API 先返回/关联 UserWeekRun reallocation，再由其派生各项目 EventDrivenReplanning；不能直接并行创建多个各自修改容量的项目运行。明确执行事实直接写 TaskEvent；当前任务明确阻塞才进入 temporary，轻微感受先进入 observe。

### 2.6 PlanningRun 与 Proposal

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/planning-runs/{run_id}` | 查询异步运行 |
| GET | `/planning-runs/{run_id}/proposal-set` | 获取候选方案集合及原子批次 |
| GET | `/proposal-sets/{proposal_set_id}` | 获取拆批顺序与汇总状态 |
| GET | `/proposals/{proposal_id}` | Proposal、命令摘要和版本 |
| POST | `/proposals/{proposal_id}/decisions` | 接受或拒绝 |

确认请求：

```json
{
  "decision": "accept",
  "expected_status": "pending_confirmation",
  "expected_versions": {
    "route_revision": 8,
    "plan_revision": 16,
    "allocation_revision": 6
  }
}
```

确认接口针对单个原子 Proposal 重新校验 expires_at、状态、版本、命令前置条件和容量。失败不会部分应用。一个 PlanningRun 可以通过 ProposalSet 返回多个 Proposal；客户端仅对 `pending_confirmation` 批次展示确认操作。

### 2.7 Materials

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/materials/upload-sessions` | 校验元数据并返回短期上传 URL |
| POST | `/materials/{material_id}/complete-upload` | 校验 checksum 后进入扫描 |
| GET | `/materials/{material_id}` | 查询扫描、解析和摘要状态 |
| DELETE | `/materials/{material_id}` | 删除材料与后续解析数据 |

上传 session 请求声明文件名、大小、MIME 和 SHA-256。对象存储事件不能直接触发解析；必须先完成后端 complete-upload 与安全扫描。

### 2.8 Notifications

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/notification-settings` | 通知设置 |
| PATCH | `/notification-settings` | 更新订阅偏好 |
| POST | `/wechat/subscription-consents` | 保存微信订阅授权结果 |

`GET/PATCH /notification-settings` 映射 `NotificationPreference`，更新使用 revision/条件写防止并发覆盖。`POST /wechat/subscription-consents` 写入 `WeChatSubscriptionConsent`；一次性授权在创建发送记录时原子地从 `granted` 变为 `consumed`。`NotificationDelivery` 记录使用的偏好版本和授权记录，发送失败不把一次性授权恢复为可用。

---

## 三、异步轮询协议

### 3.1 PlanningRun 响应

```json
{
  "id": "019...",
  "workflow_type": "weekly_review",
  "status": "running",
  "progress": {
    "phase": "model_invocation",
    "percent": null
  },
  "result": null,
  "error": null,
  "poll_after_ms": 2000,
  "created_at": "2026-07-13T00:00:00Z",
  "updated_at": "2026-07-13T00:00:03Z"
}
```

只在能可靠计算时返回 percent，不能伪造精确进度。

终态：`succeeded / failed / dead / cancelled`。客户端到达终态后停止轮询。

### 3.2 轮询退避

- 前 10 秒：1.5—2 秒；
- 10—60 秒：3—5 秒；
- 60 秒后：10 秒；
- 客户端进入后台时停止高频轮询；
- 回到前台先查询一次；
- 服务端可通过 `Retry-After` 覆盖建议间隔。

默认不依赖 SSE/WebSocket。以后增加推送只作为减少轮询的优化，不改变 PlanningRun 资源模型。

---

## 四、错误码

### 4.1 通用

| HTTP | code | 含义 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 请求字段错误 |
| 401 | `AUTH_REQUIRED` | 未登录或 token 失效 |
| 403 | `RESOURCE_FORBIDDEN` | 资源不属于用户或操作无权限 |
| 404 | `RESOURCE_NOT_FOUND` | 资源不存在 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 同 key 请求体不同 |
| 409 | `STATE_TRANSITION_NOT_ALLOWED` | 非法状态迁移 |
| 429 | `RATE_LIMITED` | 用户或供应商限流 |
| 503 | `DEPENDENCY_UNAVAILABLE` | 外部依赖不可用 |

### 4.2 规划领域

| HTTP | code | 含义 |
|---|---|---|
| 409 | `ROUTE_REVISION_CONFLICT` | 路线版本变化 |
| 409 | `PLAN_REVISION_CONFLICT` | 周计划版本变化 |
 | 409 | `PREFERENCE_REVISION_CONFLICT` | 容量或偏好变化 |
| 409 | `PROJECT_REVISION_CONFLICT` | 目标、截止或项目优先级已变化 |
| 409 | `ALLOCATION_REVISION_CONFLICT` | 项目预算变化 |
| 409 | `TASK_PRECONDITION_CHANGED` | 任务状态/版本变化 |
| 409 | `PROPOSAL_EXPIRED` | Proposal 已过期 |
| 409 | `PROPOSAL_INVALIDATED` | Proposal 依赖状态变化 |
| 422 | `CAPACITY_EXCEEDED` | 用户周或项目预算超限 |
| 422 | `DEADLINE_CAPACITY_EXCEEDED` | 截止前 required 任务累计量超过有效剩余容量 |
| 422 | `TASK_DEPENDENCY_CYCLE` | 任务硬依赖形成环 |
| 422 | `FROZEN_MILESTONE` | 尝试修改冻结里程碑 |
| 422 | `HARD_PREREQUISITE_MISSING` | 客观前置条件未满足 |
| 503 | `PLANNING_TEMPORARILY_UNAVAILABLE` | 规划异步服务暂不可用 |

错误 details 只返回客户端可安全使用的信息，不泄漏其他用户 ID、模型原始输出和内部堆栈。

---

## 五、事务与并发伪代码

### 5.1 周一确保安全基线

```text
ensure_user_week_active(user_id, week_start):
  begin transaction
    run = get_or_create rollover UserWeekRun(user_id, week_start)
    current_capacity = get_or_create UserWeekCapacity(user_id, week_start) for update
    next_capacity = get_or_create UserWeekCapacity(user_id, week_start + 7 days) for update
    lock capacities ordered by week_start
    current_set = select active UserWeekAllocationSet(current_capacity) for update
    current_allocations = select its items order by project_id for update

    if run.promotion already completed:
      return existing result

    for each current allocation ordered by project_id:
      project = lock referenced Project
      if project.status != active or allocation.status == unfunded:
        continue
      plan = get prepared WeekPlan(project, week_start) for update
      if plan exists:
        promote plan to active
        activate allocation
      else if allocation.budget_minutes > 0 and not deadline_week(project) and not calibration_hold(project):
        create empty active baseline
        record anomaly

    mark promotion_completed
    create next-week UserWeekAllocationSet revision and allocation items under next_capacity
    for each next-week allocation where status=reserved and budget_minutes > 0:
      project = referenced Project
      if project.status == active and not deadline_week(project) and not calibration_hold(project):
        get_or_create empty prepared WeekPlan bound to the new allocation item
        create OutboxMessage for project WeeklyReview
      else:
        mark allocation as released or unfunded according to reason
  commit
```

该函数可由 Scheduler 或小程序周一首次打开调用，依赖数据库唯一约束保证只成功一次。

### 5.2 应用项目 Proposal

```text
apply_proposal(proposal_id, decision):
  begin transaction
    proposal = select proposal for update
    validate status and expires_at

    capacity = select relevant UserWeekCapacity for update
    allocation_set = select UserWeekAllocationSet for update
    allocation = select its UserWeekAllocation item for update
    project = select Project for update
    week_plans = select affected plans for update
    targets = select affected tasks/milestones for update

    validate revision vector
    load task events after project task_event_revision
    validate each expected_state
    calculate computed permissions
    simulate commands and totals
    verify project budget and user capacity

    execute command batch
    update aggregate minutes and revisions
    record ProposalDecision
    create required OutboxMessages
  commit
```

锁顺序必须与数据模型文档一致。

### 5.3 TaskEvent 写入

```text
append_task_event(task_id, request):
  refs = resolve user_id, week_start, allocation_id, project_id without row locks
  begin transaction
    lookup prior idempotent result
    capacity = select UserWeekCapacity(refs.user_id, refs.week_start) for update
    allocation_set = select WeekPlan.referenced UserWeekAllocationSet for update
    allocation = select WeekPlan.referenced UserWeekAllocation for update
    project = select referenced Project for update
    week_plan = select referenced WeekPlan for update
    task = select Task(task_id) for update
    verify locked ownership chain still matches refs
    verify expected_task_version
    verify transition
    before_consumed = effective_consumed(task)
    next_revision = project.task_event_revision + 1
    insert TaskEvent(project_event_revision = next_revision)
    update Project.task_event_revision = next_revision
    update Task status/version
    after_consumed = effective_consumed(task)
    update WeekPlan, Allocation and UserWeekCapacity summaries by after_consumed - before_consumed
    revalidate user capacity and deadline feasibility when relevant
  commit
```

TaskEvent 不允许先锁 Project/Task 后再更新容量汇总。`referenced` 指该 WeekPlan 原本绑定的 AllocationSet/Allocation，不是当前 active 集合；因此 settled 或 superseded 历史周仍可安全补记实际耗时。即使某类事件当前不改变 actual_minutes，也使用同一锁序，避免后续事件类型扩展重新引入死锁分支。

### 5.4 截止前可行性校验

```text
validate_deadline_feasibility(user_id, week_start, proposed_tasks):
  capacity = load UserWeekCapacity and available_weekdays
  normal_days = count(effective available weekdays in full week)
  earliest_cutoff = business_date if week_start is current week else week_start
  reject proposed due_date earlier than earliest_cutoff
  effective_consumed(task) = task.actual_minutes if not null
                             else task.estimated_minutes if task.first_completed_at is not null
                             else 0
  remaining_estimated(task) = 0 if task is terminal
                              else max(0, task.estimated_minutes - coalesce(task.actual_minutes, 0))
  consumed_to_date = sum effective_consumed for all tasks already belonging to this UserWeek
  canonicalize each task:
    due_date = explicit allowed constraint
               or inherited project target_date boundary when target_date is in this week
               or null
    exam/event target uses target_date - 1 effective cutoff
    delivery target uses target_date inclusive

  for cutoff in distinct due_date ordered ascending:
    if normal_days == 0:
      available = 0
    else:
      cumulative_capacity = floor(
        allocatable_minutes * count(effective available days from week_start through cutoff)
        / normal_days
      )
      available = max(0, cumulative_capacity - consumed_to_date)
    required = sum remaining_estimated(task) across all existing unfinished and proposed tasks in all projects
               where necessity=required and effective_due_date <= cutoff
    if required > available:
      raise DEADLINE_CAPACITY_EXCEEDED(cutoff, available, required, overflow)

  verify total planned minutes <= allocatable_minutes
  verify each project total <= allocation budget
```

该算法只按日计数做累计容量折算，不生成每日计划，也不持久化额外的 remaining 字段。未登记实际耗时时，未完成任务的待安排量就是完整 estimated_minutes；登记部分实际耗时后，待安排量派生为 `max(0, estimated_minutes - actual_minutes)`；任务完成后待安排量为 0。这样预计 100、已投入 40、尚未完成的任务合计仍占 100，而不是 140。若实际投入已超过预计，则 consumed_to_date 保留真实投入、待安排量归零。当前周拒绝早于业务日期的截止点，因此所有有效截止点统一扣除校验时本周已记录的 `consumed_to_date`；预备周该值为 0。每个任务完整归属一个 effective_due_date；跨截止点工作先拆分任务。Proposal 预检执行一次，应用事务在锁定 Capacity/Allocation/WeekPlan 后再次执行，避免并发项目分别重复使用同一截止前容量。

---

## 六、Outbox Dispatcher 与 Celery

### 6.1 Dispatcher 循环

```text
loop:
  begin transaction
    rows = select due pending or expired-claimed messages
           order by created_at
           for update skip locked
           limit batch_size
    mark rows claimed with lease
  commit

  for row in rows:
    publish message ID and routing metadata to target queue
    on broker confirm: mark published
    on failure: return to pending with next_retry_at
```

Celery payload只传 `outbox_message_id`、`planning_run_id` 等 ID，不传完整 Snapshot 或材料正文。

### 6.2 初始配置

所有数值通过配置管理并记录配置版本，以下为默认起点：

| 队列 | soft limit | hard limit | 最大业务重试 | worker prefetch |
|---|---:|---:|---:|---:|
| planning_interactive | 90s | 120s | 2 | 1 |
| planning_weekly | 120s | 150s | 3 | 1 |
| material | 300s | 360s | 2 | 1 |
| notification | 15s | 30s | 5 | 10 |

Celery：

- `task_acks_late=true`；
- `task_reject_on_worker_lost=true`；
- Worker 执行前锁定 PlanningRun 并检查状态和幂等键；
- Worker 可将 pending、queued 或到期 retry_wait 原子更新为 running，以处理 Broker 快速投递竞态；
- 领取时通过 CAS 写入 `lease_owner / lease_expires_at / heartbeat_at`，执行期间周期续租；只有仍持有 lease_owner 的 Worker 能写 succeeded/retry_wait/failed/dead；
- Dispatcher 发布成功后只在 PlanningRun 仍为 pending 时补写 queued，绝不覆盖 running/succeeded；
- 可重试异常指数退避并加入随机抖动；
- 模型 4xx 配置错误、Schema 永久不兼容等不可重试；
- 超过最大次数将 PlanningRun 置为 dead，并告警。

PlanningRun 恢复扫描器不依赖被 hard kill 的进程善后：

```text
recover_expired_planning_runs(now):
  select running where lease_expires_at < now
    for update skip locked
  for each run:
    if attempt_count >= max_attempts:
      CAS running + old lease → dead
    else:
      CAS running + old lease → retry_wait
      clear lease fields
      set next_retry_at with backoff
      create idempotent OutboxMessage for retry
```

旧 Worker 在租约过期后即使重新运行，也必须因终态 CAS 不匹配而放弃结果。

Outbox：

- claim lease 初始 30 秒；
- 每批最多 100 条；
- 投递退避从 5 秒开始，最大 5 分钟；
- 最大投递 10 次后进入 dead；
- Dispatcher 心跳和 dead 数量纳入告警。

### 6.3 供应商限流与成本

Redis token bucket 按供应商和模型控制：

- 并发请求；
- 每分钟请求数；
- 每分钟 token；
- 每日成本预算；
- 单用户短时规划频率。

调度优先级：

1. 已到期但尚未生成计划的用户周任务；
2. 用户前台主动发起的初始规划与事件驱动重规划；
3. 普通周评估；
4. 材料摘要和低优先级后台任务。

达到成本预算时停止非必要后台任务，保留安全基线，不用低质量未验证结果替代。

---

## 七、Scheduler

### 7.1 固定时区

所有扫描使用 `Asia/Shanghai`。数据库时间戳使用 UTC，但 week_start 由上海本地日期计算。

### 7.2 扫描策略

- 每分钟扫描一次需要确保安全基线的用户；
- 每日扫描 target_date 尚未过去的 active Project，重算截止前剩余 required 工作量与剩余容量；infeasible 时幂等产生 deadline_risk 并立即进入 EventDrivenReplanning，不等待趋势窗口；paused 项目只更新风险提示，不创建 PlanningRun，恢复后再规划；
- 每日扫描所有满足 `target_date < 上海业务日期` 的 planning/active/paused Project，执行幂等 DeadlineClosure：Project 转 closed、terminal_reason=deadline_reached，closed 未完成路线对象，cancelled 所有仍为 planned 的任务并记录 project_deadline_reached，创建 ProjectClosureSnapshot，取消未终结 PlanningRun、失效未应用 Proposal，并停止后续预备周；
- 周一零点后优先执行不调用模型的基线晋升；
- AI 周评估随后按批次和供应商限流逐步入队；
- 周中扫描残留 pending/partial_failed UserWeekRun；
- 每分钟扫描 `planning_runs.running` 的过期 lease 与到期 retry_wait，执行 CAS 回收或重新投递；
- 用户首次打开调用 ensure-active 作为后台调度兜底；
- 所有扫描通过数据库唯一约束和 SKIP LOCKED 支持安全重入。

同一用户周发生并发事件时遵循最低必要顺序：DeadlineClosure 优先于该项目的一切规划写入；其后才是安全基线晋升、目标/截止确认、用户级容量版本变更和普通项目规划。新的 Project 状态、AllocationSet/route_revision/plan_revision 使旧 Snapshot 与 Proposal 失效；EventDrivenReplanning 完成后再生成新的 WeeklyReview。依靠行锁、revision 和 CAS 保证，不引入复杂全局优先级队列。

### 7.3 单活到多实例

Scheduler 默认单活。健康检查连续失败时由部署平台重启。

后续多实例无需改业务协议：扫描候选 UserWeekRun 时使用 `FOR UPDATE SKIP LOCKED` 抢占，并继续依靠数据库幂等约束。

---

## 八、文件上传安全

### 8.1 上传流程

```text
声明文件元数据
→ 后端校验大小/MIME/扩展名
→ 获得短期签名上传 URL
→ 客户端直传私有对象存储
→ complete-upload 校验大小与 SHA-256
→ 恶意文件扫描
→ clean 后进入隔离解析队列
→ 生成脱敏摘要
```

### 8.2 材料能力开放限制

- 单文件大小和用户总存储配额由配置控制；
- 只开放明确白名单格式；
- 校验声明 MIME、扩展名和 magic bytes；
- 压缩包默认不支持，避免 zip bomb 和嵌套解析；
- 解析容器限制 CPU、内存、执行时间和网络访问；
- 原始文件与解析结果均为私有；
- 材料文字作为不可信数据块传入模型，不拼接进系统指令区域。

---

## 九、代码目录

```text
backend/
  app/
    main.py
    core/
      config.py
      clock.py
      errors.py
      security.py
      observability.py
    modules/
      identity/
        domain/
        application/
        infrastructure/
        api/
      planning/
        domain/
          entities.py
          value_objects.py
          commands.py
          policies.py
          state_machines.py
        application/
          services.py
          command_handlers.py
          user_week_coordinator.py
        infrastructure/
          models.py
          repositories.py
        api/
      tasks/
      feedback/
      materials/
      notifications/
      ai_orchestration/
        workflows/
        schemas/
        context_builder/
        model_gateway/
        validators/
    infrastructure/
      database/
      outbox/
      celery/
      object_storage/
    workers/
      planning.py
      materials.py
      notifications.py
      scheduler.py
      outbox_dispatcher.py
  migrations/
  tests/
    unit/
    integration/
    contract/
    evaluation/
    e2e/

clients/
  miniapp/
    src/
    generated-api/
```

领域模块不能导入 FastAPI、Celery 或供应商 SDK。基础设施通过接口注入。

小程序采用原生微信小程序 + TypeScript，复用自动生成的 API 类型与客户端。Web/App 复用 API 契约和部分无 UI 业务类型，不强求共用一套界面代码；交付顺序后续另行设计。

---

## 十、配置与密钥

配置分为：

- 非敏感运行配置：环境变量或配置文件；
- 敏感密钥：云密钥管理服务；
- 可动态调整策略：数据库中的版本化 policy 配置；
- Prompt 与 JSON Schema：代码版本管理并记录版本号。

启动时校验必需配置，缺失关键密钥直接失败，不使用测试默认值进入生产。

---

## 十一、CI/CD 质量门

每次合并必须通过：

1. Ruff/格式检查；
2. mypy 或 pyright 类型检查；
3. 单元测试；
4. PostgreSQL/Redis 集成测试；
5. Alembic 迁移前进测试；
6. OpenAPI 兼容性检查；
7. JSON Schema 契约测试；
8. 安全依赖扫描和密钥扫描；
9. 关键 AI 离线评测集；
10. Docker 镜像构建。

生产发布采用滚动部署。数据库迁移遵循先兼容旧代码、再发布新代码、最后清理旧字段的扩展/收缩模式。

---

## 十二、实现依赖顺序

这是架构依赖顺序，不是具体开发任务清单：

1. 项目骨架、配置、数据库、Clock、错误模型；
2. 身份、用户偏好、Project/Stage/Milestone；
3. UserWeekCapacity、Allocation、WeekPlan、TaskEvent；
4. 领域状态机、容量策略、锁顺序和 revision；
5. Outbox、Dispatcher、PlanningRun lease、恢复扫描器、Celery 与 Scheduler；
6. Snapshot、PlanningRun、ProposalSet 与假 ModelGateway；
7. 初始规划命令与 Proposal 原子批次应用；
8. 建立完整方案核心 AI 评测集并接入 CI；
9. 接入真实 ModelGateway，通过评测门后再进入 staging；
10. 小程序初始规划、任务和轮询闭环；
11. 周一基线、AllocationSet、prepared 壳计划与 WeeklyReview；
12. 首次规划在残周不少于/少于 4 天时分别创建两周/三周初始窗口，并校验每周容量与 allocation 绑定；
13. 周中暂停释放未锁定预算、supersede 当前及后续计划、取消未开始任务，并只允许其他 active 项目参与重分配；
14. Feedback、ProjectWeekAssessment 与 EventDrivenReplanning；
15. 剩余路线校准、材料、通知和运营监控。

每一步完成后都应有可运行的垂直切片，避免最后才集成 AI、队列和事务。

---

## 十三、上线前容量基线

压测至少验证：

- 1 万用户、平均 3 个 active 项目的周一基线晋升；
- UserWeekRun 重复调度和 Worker 重复投递；
- 规划队列在供应商限流下的积压恢复；
- 100 个并发 Proposal 应用不会突破用户周容量；
- Outbox Dispatcher 多实例 claim 无重复副作用；
- PostgreSQL 锁等待、死锁率和慢查询；
- 模型超时 30 分钟时用户仍能读取和执行安全基线。

压测目标值在部署容量估算阶段结合实际供应商配额和云资源确定，不能在没有测量时承诺固定吞吐量。
