from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.modules.tasks.domain.task_events import (
    Necessity,
    Task,
    TaskEventCommand,
    TaskEventType,
    TaskKind,
    TaskStatus,
    apply_task_event,
    assert_acyclic_dependencies,
    effective_consumed,
)

NOW = datetime(2026, 7, 16, 10, tzinfo=UTC)


def task(status: TaskStatus = TaskStatus.PLANNED) -> Task:
    completed_at = NOW if status is TaskStatus.COMPLETED else None
    return Task(
        id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        week_plan_id=uuid4(),
        source_milestone_id=uuid4(),
        origin_task_id=None,
        title="Task",
        description="",
        task_kind=TaskKind.MAIN,
        estimated_minutes=100,
        actual_minutes=None,
        first_completed_at=completed_at,
        necessity=Necessity.REQUIRED,
        due_date=date(2026, 7, 20),
        order_key=1,
        status=status,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def command(
    event_type: TaskEventType, version: int, actual_minutes: int | None = None
) -> TaskEventCommand:
    return TaskEventCommand(event_type, version, actual_minutes, None, None, NOW)


def test_duration_complete_reopen_and_defer_preserve_cumulative_actual_minutes() -> None:
    aggregate = task()
    duration = apply_task_event(aggregate, command(TaskEventType.DURATION_RECORDED, 1, 40), NOW)
    assert (duration.before_consumed, duration.after_consumed) == (0, 40)

    apply_task_event(aggregate, command(TaskEventType.COMPLETED, 2), NOW)
    first_completed = aggregate.first_completed_at
    apply_task_event(aggregate, command(TaskEventType.REOPENED, 3), NOW + timedelta(minutes=1))
    apply_task_event(aggregate, command(TaskEventType.DEFERRED, 4), NOW + timedelta(minutes=2))

    assert aggregate.status is TaskStatus.DEFERRED
    assert aggregate.actual_minutes == 40
    assert aggregate.first_completed_at == first_completed
    assert effective_consumed(aggregate) == 40
    assert aggregate.version == 5


def test_completion_without_actual_minutes_consumes_estimate() -> None:
    aggregate = task()
    result = apply_task_event(aggregate, command(TaskEventType.COMPLETED, 1), NOW)
    assert result.before_consumed == 0
    assert result.after_consumed == 100
    assert aggregate.first_completed_at == NOW


def test_duration_is_cumulative_overwrite_not_addition() -> None:
    aggregate = task()
    apply_task_event(aggregate, command(TaskEventType.DURATION_RECORDED, 1, 40), NOW)
    result = apply_task_event(aggregate, command(TaskEventType.DURATION_RECORDED, 2, 65), NOW)
    assert result.before_consumed == 40
    assert result.after_consumed == 65
    assert aggregate.actual_minutes == 65


def test_version_conflict_and_illegal_transition_do_not_mutate_task() -> None:
    aggregate = task(TaskStatus.COMPLETED)
    before = (aggregate.status, aggregate.version, aggregate.first_completed_at)
    with pytest.raises(AppError) as captured:
        apply_task_event(aggregate, command(TaskEventType.SKIPPED, 1), NOW)
    assert captured.value.code == "STATE_TRANSITION_NOT_ALLOWED"
    assert (aggregate.status, aggregate.version, aggregate.first_completed_at) == before

    with pytest.raises(AppError) as captured:
        apply_task_event(aggregate, command(TaskEventType.REOPENED, 99), NOW)
    assert captured.value.code == "TASK_VERSION_CONFLICT"
    assert (aggregate.status, aggregate.version, aggregate.first_completed_at) == before


def test_dependency_graph_accepts_dag_and_rejects_cycle_and_self_edge() -> None:
    first, second, third = uuid4(), uuid4(), uuid4()
    assert_acyclic_dependencies([(first, second), (second, third)])
    with pytest.raises(AppError) as captured:
        assert_acyclic_dependencies([(first, second), (second, third), (third, first)])
    assert captured.value.code == "TASK_DEPENDENCY_CYCLE"
    with pytest.raises(AppError):
        assert_acyclic_dependencies([(first, first)])
