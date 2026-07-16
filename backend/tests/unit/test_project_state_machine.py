from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.modules.planning.domain.projects import (
    Confidence,
    DeadlineDayPolicy,
    GoalType,
    Project,
    ProjectStatus,
    TerminalReason,
)
from app.modules.planning.domain.state_machines import ALLOWED_TRANSITIONS, transition_project

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def project(status: ProjectStatus) -> Project:
    reason = None
    ended_at = None
    if status is ProjectStatus.COMPLETED:
        reason, ended_at = TerminalReason.USER_COMPLETED, NOW
    elif status is ProjectStatus.CLOSED:
        reason, ended_at = TerminalReason.DEADLINE_REACHED, NOW
    return Project(
        id=uuid4(),
        user_id=uuid4(),
        name="Project",
        description="Goal",
        goal_type=GoalType.OUTCOME,
        predecessor_project_id=None,
        status=status,
        target_date=date(2026, 8, 1),
        deadline_day_policy=DeadlineDayPolicy.DATE_INCLUSIVE,
        priority=50,
        minimum_weekly_minutes=0,
        confidence=Confidence.LOW,
        route_revision=1,
        plan_revision=1,
        project_revision=1,
        task_event_revision=0,
        terminal_reason=reason,
        ended_at=ended_at,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    ("source", "target"),
    [(source, target) for source, targets in ALLOWED_TRANSITIONS.items() for target in targets],
)
def test_every_declared_project_transition_is_executable(
    source: ProjectStatus, target: ProjectStatus
) -> None:
    aggregate = project(source)
    reason = None
    if target is ProjectStatus.COMPLETED:
        reason = TerminalReason.USER_COMPLETED
    elif target is ProjectStatus.CLOSED:
        reason = TerminalReason.DEADLINE_REACHED
    result = transition_project(aggregate, target, NOW, terminal_reason=reason)
    assert result.previous is source
    assert aggregate.status is target
    assert aggregate.project_revision == 2


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (ProjectStatus.DRAFT, ProjectStatus.COMPLETED),
        (ProjectStatus.PAUSED, ProjectStatus.COMPLETED),
        (ProjectStatus.CLOSED, ProjectStatus.ACTIVE),
        (ProjectStatus.ARCHIVED, ProjectStatus.ACTIVE),
    ],
)
def test_illegal_project_transition_has_no_mutation(
    source: ProjectStatus, target: ProjectStatus
) -> None:
    aggregate = project(source)
    before = (aggregate.status, aggregate.project_revision, aggregate.terminal_reason)
    with pytest.raises(AppError) as captured:
        transition_project(aggregate, target, NOW)
    assert captured.value.code == "STATE_TRANSITION_NOT_ALLOWED"
    assert (aggregate.status, aggregate.project_revision, aggregate.terminal_reason) == before


def test_archiving_completed_project_preserves_terminal_fact() -> None:
    aggregate = project(ProjectStatus.COMPLETED)
    ended_at = aggregate.ended_at
    transition_project(aggregate, ProjectStatus.ARCHIVED, NOW)
    assert aggregate.terminal_reason is TerminalReason.USER_COMPLETED
    assert aggregate.ended_at == ended_at
