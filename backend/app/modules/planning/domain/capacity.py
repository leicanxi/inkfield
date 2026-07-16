from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from app.core.errors import AppError
from app.modules.planning.domain.projects import ProjectStatus


class CapacityStatus(StrEnum):
    DRAFT = "draft"
    ALLOCATED = "allocated"
    ACTIVE = "active"
    SETTLED = "settled"


class AllocationSetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    SETTLED = "settled"


class AllocationStatus(StrEnum):
    RESERVED = "reserved"
    ACTIVE = "active"
    UNFUNDED = "unfunded"
    RELEASED = "released"
    SETTLED = "settled"


class AllocationReason(StrEnum):
    SCHEDULED = "scheduled"
    CAPACITY_SHORTAGE = "capacity_shortage"


class AllocationSetReason(StrEnum):
    INITIAL = "initial"
    ROLLOVER = "rollover"
    NEW_PROJECT = "new_project"
    CAPACITY_CHANGE = "capacity_change"
    RECOVERY = "recovery"


class DeadlineRisk(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UserWeekRunType(StrEnum):
    ROLLOVER = "rollover"
    REALLOCATION = "reallocation"
    RECOVERY = "recovery"


class UserWeekRunStatus(StrEnum):
    PENDING = "pending"
    PROMOTING_BASELINE = "promoting_baseline"
    ALLOCATING = "allocating"
    DISPATCHING_PROJECTS = "dispatching_projects"
    PLANNING_PROJECTS = "planning_projects"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


RUN_TRANSITIONS: dict[UserWeekRunStatus, frozenset[UserWeekRunStatus]] = {
    UserWeekRunStatus.PENDING: frozenset(
        {UserWeekRunStatus.PROMOTING_BASELINE, UserWeekRunStatus.ALLOCATING}
    ),
    UserWeekRunStatus.PROMOTING_BASELINE: frozenset(
        {UserWeekRunStatus.ALLOCATING, UserWeekRunStatus.FAILED}
    ),
    UserWeekRunStatus.ALLOCATING: frozenset(
        {UserWeekRunStatus.DISPATCHING_PROJECTS, UserWeekRunStatus.FAILED}
    ),
    UserWeekRunStatus.DISPATCHING_PROJECTS: frozenset({UserWeekRunStatus.PLANNING_PROJECTS}),
    UserWeekRunStatus.PLANNING_PROJECTS: frozenset(
        {UserWeekRunStatus.COMPLETED, UserWeekRunStatus.PARTIAL_FAILED}
    ),
    UserWeekRunStatus.PARTIAL_FAILED: frozenset(
        {UserWeekRunStatus.PLANNING_PROJECTS, UserWeekRunStatus.COMPLETED}
    ),
    UserWeekRunStatus.FAILED: frozenset({UserWeekRunStatus.PENDING}),
    UserWeekRunStatus.COMPLETED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ProjectDemand:
    project_id: UUID
    status: ProjectStatus
    priority: int
    minimum_minutes: int
    desired_minutes: int
    planned_minutes: int
    actual_minutes: int
    project_revision: int
    deadline_risk: DeadlineRisk = DeadlineRisk.NONE

    @property
    def locked_minutes(self) -> int:
        return max(self.planned_minutes, self.actual_minutes)


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    project_id: UUID
    budget_minutes: int
    minimum_minutes: int
    priority_snapshot: int
    project_revision_snapshot: int
    deadline_risk: DeadlineRisk
    allocation_reason: AllocationReason
    status: AllocationStatus
    planned_minutes: int
    actual_minutes: int


_RISK_ORDER = {
    DeadlineRisk.HIGH: 0,
    DeadlineRisk.MEDIUM: 1,
    DeadlineRisk.LOW: 2,
    DeadlineRisk.NONE: 3,
}


def allocate_project_budgets(
    allocatable_minutes: int, demands: list[ProjectDemand], *, prepared: bool
) -> tuple[BudgetDecision, ...]:
    if allocatable_minutes < 0:
        raise AppError("CAPACITY_INVALID", "Allocatable capacity cannot be negative.")
    active = [demand for demand in demands if demand.status is ProjectStatus.ACTIVE]
    for demand in active:
        if (
            not 1 <= demand.priority <= 100
            or demand.project_revision < 1
            or min(
                demand.minimum_minutes,
                demand.desired_minutes,
                demand.planned_minutes,
                demand.actual_minutes,
            )
            < 0
        ):
            raise AppError("ALLOCATION_INPUT_INVALID", "Project demand contains invalid values.")
        if demand.desired_minutes < demand.locked_minutes:
            raise AppError(
                "ALLOCATION_BELOW_LOCKED_WORK",
                "Desired budget cannot be lower than already planned or consumed work.",
                status_code=409,
                details={"project_id": str(demand.project_id)},
            )
    locked_total = sum(demand.locked_minutes for demand in active)
    if locked_total > allocatable_minutes:
        raise AppError(
            "CAPACITY_LOCKED_WORK_EXCEEDED",
            "Existing planned or consumed work exceeds allocatable capacity.",
            status_code=409,
            details={"locked": locked_total, "allocatable": allocatable_minutes},
        )

    ordered = sorted(
        active,
        key=lambda demand: (
            _RISK_ORDER[demand.deadline_risk],
            -demand.priority,
            str(demand.project_id),
        ),
    )
    budgets = {demand.project_id: demand.locked_minutes for demand in ordered}
    remaining = allocatable_minutes - locked_total

    for demand in ordered:
        floor = max(demand.locked_minutes, demand.minimum_minutes)
        needed = floor - budgets[demand.project_id]
        if needed <= remaining:
            budgets[demand.project_id] += needed
            remaining -= needed

    for demand in ordered:
        desired = max(demand.desired_minutes, budgets[demand.project_id])
        granted = min(remaining, desired - budgets[demand.project_id])
        budgets[demand.project_id] += granted
        remaining -= granted
        if remaining == 0:
            break

    decisions: list[BudgetDecision] = []
    for demand in ordered:
        budget = budgets[demand.project_id]
        unfunded = budget == 0
        decisions.append(
            BudgetDecision(
                project_id=demand.project_id,
                budget_minutes=budget,
                minimum_minutes=demand.minimum_minutes,
                priority_snapshot=demand.priority,
                project_revision_snapshot=demand.project_revision,
                deadline_risk=demand.deadline_risk,
                allocation_reason=(
                    AllocationReason.CAPACITY_SHORTAGE if unfunded else AllocationReason.SCHEDULED
                ),
                status=(
                    AllocationStatus.UNFUNDED
                    if unfunded
                    else AllocationStatus.RESERVED
                    if prepared
                    else AllocationStatus.ACTIVE
                ),
                planned_minutes=demand.planned_minutes,
                actual_minutes=demand.actual_minutes,
            )
        )
    if sum(decision.budget_minutes for decision in decisions) > allocatable_minutes:
        raise AssertionError("allocation policy overcommitted user capacity")
    return tuple(decisions)


def transition_user_week_run(
    current: UserWeekRunStatus, target: UserWeekRunStatus
) -> UserWeekRunStatus:
    if target not in RUN_TRANSITIONS[current]:
        raise AppError(
            "STATE_TRANSITION_NOT_ALLOWED",
            "The requested user-week run transition is not allowed.",
            status_code=409,
            details={"from": current.value, "to": target.value},
        )
    return target


def validate_week_start(value: date) -> None:
    if value.weekday() != 0:
        raise AppError("WEEK_START_INVALID", "week_start must be a Monday.")


@dataclass(frozen=True, slots=True)
class UserWeekSummary:
    capacity_id: UUID
    user_id: UUID
    week_start: date
    total_minutes: int
    allocatable_minutes: int
    buffer_minutes: int
    allocated_minutes: int
    planned_minutes: int
    actual_minutes: int
    status: CapacityStatus
    active_allocation_revision: int
    allocations: tuple[BudgetDecision, ...]
    updated_at: datetime
