from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.core.errors import AppError
from app.modules.planning.domain.capacity import (
    AllocationReason,
    AllocationStatus,
    DeadlineRisk,
    ProjectDemand,
    UserWeekRunStatus,
    allocate_project_budgets,
    transition_user_week_run,
)
from app.modules.planning.domain.projects import ProjectStatus


def demand(
    *,
    project_id: UUID | None = None,
    status: ProjectStatus = ProjectStatus.ACTIVE,
    priority: int = 50,
    minimum: int = 0,
    desired: int = 0,
    planned: int = 0,
    actual: int = 0,
    risk: DeadlineRisk = DeadlineRisk.NONE,
) -> ProjectDemand:
    return ProjectDemand(
        project_id=project_id or uuid4(),
        status=status,
        priority=priority,
        minimum_minutes=minimum,
        desired_minutes=desired,
        planned_minutes=planned,
        actual_minutes=actual,
        project_revision=1,
        deadline_risk=risk,
    )


def test_allocation_protects_locked_work_then_prioritizes_risk_and_minimum() -> None:
    locked = demand(priority=10, minimum=0, desired=80, planned=60)
    urgent = demand(priority=20, minimum=50, desired=100, risk=DeadlineRisk.HIGH)
    normal = demand(priority=100, minimum=50, desired=100)

    result = allocate_project_budgets(140, [normal, locked, urgent], prepared=False)
    budgets = {item.project_id: item.budget_minutes for item in result}

    assert budgets[locked.project_id] == 60
    assert budgets[urgent.project_id] == 80
    assert budgets[normal.project_id] == 0
    assert sum(budgets.values()) == 140


def test_paused_project_is_excluded_and_zero_budget_is_explicitly_unfunded() -> None:
    funded = demand(priority=100, minimum=30, desired=30)
    unfunded = demand(priority=1, minimum=30, desired=30)
    paused = demand(status=ProjectStatus.PAUSED, desired=100)

    result = allocate_project_budgets(30, [unfunded, paused, funded], prepared=True)
    by_project = {item.project_id: item for item in result}

    assert paused.project_id not in by_project
    assert by_project[funded.project_id].status is AllocationStatus.RESERVED
    assert by_project[unfunded.project_id].status is AllocationStatus.UNFUNDED
    assert by_project[unfunded.project_id].allocation_reason is AllocationReason.CAPACITY_SHORTAGE


def test_locked_work_over_capacity_fails_without_partial_result() -> None:
    with pytest.raises(AppError) as captured:
        allocate_project_budgets(
            59,
            [demand(desired=60, planned=40, actual=60)],
            prepared=False,
        )
    assert captured.value.code == "CAPACITY_LOCKED_WORK_EXCEEDED"


@pytest.mark.parametrize("priority", [0, 101])
def test_invalid_priority_is_rejected(priority: int) -> None:
    with pytest.raises(AppError) as captured:
        allocate_project_budgets(60, [demand(priority=priority, desired=60)], prepared=False)
    assert captured.value.code == "ALLOCATION_INPUT_INVALID"


def test_user_week_run_recovery_path_and_illegal_terminal_transition() -> None:
    assert (
        transition_user_week_run(
            UserWeekRunStatus.PARTIAL_FAILED, UserWeekRunStatus.PLANNING_PROJECTS
        )
        is UserWeekRunStatus.PLANNING_PROJECTS
    )
    with pytest.raises(AppError) as captured:
        transition_user_week_run(UserWeekRunStatus.COMPLETED, UserWeekRunStatus.PENDING)
    assert captured.value.code == "STATE_TRANSITION_NOT_ALLOWED"
