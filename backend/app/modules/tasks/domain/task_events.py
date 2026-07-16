from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from app.core.errors import AppError


class TaskStatus(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"
    REPLACED = "replaced"


class TaskEventType(StrEnum):
    COMPLETED = "completed"
    REOPENED = "reopened"
    SKIPPED = "skipped"
    RESTORED = "restored"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"
    REPLACED = "replaced"
    DURATION_RECORDED = "duration_recorded"


class TaskKind(StrEnum):
    MAIN = "main"
    REVIEW = "review"
    REMEDIATION = "remediation"
    EXPLORATION = "exploration"
    REST = "rest"


class Necessity(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass(slots=True)
class Task:
    id: UUID
    user_id: UUID
    project_id: UUID
    week_plan_id: UUID
    source_milestone_id: UUID
    origin_task_id: UUID | None
    title: str
    description: str
    task_kind: TaskKind
    estimated_minutes: int
    actual_minutes: int | None
    first_completed_at: datetime | None
    necessity: Necessity
    due_date: date | None
    order_key: int
    status: TaskStatus
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TaskEventCommand:
    event_type: TaskEventType
    expected_task_version: int
    actual_minutes: int | None
    reason_code: str | None
    note: str | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class TaskEventResult:
    previous_status: TaskStatus
    new_status: TaskStatus
    before_consumed: int
    after_consumed: int
    new_version: int


_TRANSITIONS = {
    (TaskStatus.PLANNED, TaskEventType.COMPLETED): TaskStatus.COMPLETED,
    (TaskStatus.COMPLETED, TaskEventType.REOPENED): TaskStatus.PLANNED,
    (TaskStatus.PLANNED, TaskEventType.SKIPPED): TaskStatus.SKIPPED,
    (TaskStatus.SKIPPED, TaskEventType.RESTORED): TaskStatus.PLANNED,
    (TaskStatus.PLANNED, TaskEventType.DEFERRED): TaskStatus.DEFERRED,
    (TaskStatus.PLANNED, TaskEventType.CANCELLED): TaskStatus.CANCELLED,
    (TaskStatus.PLANNED, TaskEventType.REPLACED): TaskStatus.REPLACED,
}


def effective_consumed(task: Task) -> int:
    if task.actual_minutes is not None:
        return task.actual_minutes
    if task.first_completed_at is not None:
        return task.estimated_minutes
    return 0


def apply_task_event(task: Task, command: TaskEventCommand, now: datetime) -> TaskEventResult:
    if task.version != command.expected_task_version:
        raise AppError(
            "TASK_VERSION_CONFLICT",
            "Task changed; reload and try again.",
            status_code=409,
            details={"expected": command.expected_task_version, "actual": task.version},
        )
    if command.actual_minutes is not None and command.actual_minutes < 0:
        raise AppError("TASK_ACTUAL_MINUTES_INVALID", "Actual minutes cannot be negative.")
    previous = task.status
    before = effective_consumed(task)
    target: TaskStatus
    if command.event_type is TaskEventType.DURATION_RECORDED:
        if command.actual_minutes is None:
            raise AppError(
                "TASK_ACTUAL_MINUTES_REQUIRED",
                "duration_recorded requires cumulative actual_minutes.",
            )
        target = previous
    else:
        transition_target = _TRANSITIONS.get((previous, command.event_type))
        if transition_target is None:
            raise AppError(
                "STATE_TRANSITION_NOT_ALLOWED",
                "The requested task transition is not allowed.",
                status_code=409,
                details={"from": previous.value, "event_type": command.event_type.value},
            )
        target = transition_target
        if command.event_type is TaskEventType.COMPLETED and task.first_completed_at is None:
            task.first_completed_at = command.occurred_at
    if command.actual_minutes is not None:
        if command.event_type not in {
            TaskEventType.COMPLETED,
            TaskEventType.DURATION_RECORDED,
        }:
            raise AppError(
                "TASK_ACTUAL_MINUTES_NOT_ALLOWED",
                "Only completed or duration_recorded may update actual minutes.",
            )
        task.actual_minutes = command.actual_minutes
    task.status = target
    task.version += 1
    task.updated_at = now
    return TaskEventResult(previous, target, before, effective_consumed(task), task.version)


def assert_acyclic_dependencies(edges: list[tuple[UUID, UUID]]) -> None:
    graph: dict[UUID, set[UUID]] = {}
    nodes: set[UUID] = set()
    for prerequisite, dependent in edges:
        if prerequisite == dependent:
            raise AppError(
                "TASK_DEPENDENCY_CYCLE",
                "A task cannot depend on itself.",
                status_code=409,
            )
        graph.setdefault(prerequisite, set()).add(dependent)
        nodes.update({prerequisite, dependent})
    visiting: set[UUID] = set()
    visited: set[UUID] = set()

    def visit(node: UUID) -> None:
        if node in visiting:
            raise AppError(
                "TASK_DEPENDENCY_CYCLE",
                "Task dependencies contain a cycle.",
                status_code=409,
            )
        if node in visited:
            return
        visiting.add(node)
        for dependent in graph.get(node, set()):
            visit(dependent)
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        visit(node)
