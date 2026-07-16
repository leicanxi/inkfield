from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class GoalType(StrEnum):
    DEADLINE = "deadline"
    OUTCOME = "outcome"
    CAPABILITY = "capability"
    CONTINUOUS = "continuous"


class DeadlineDayPolicy(StrEnum):
    EVENT_EXCLUSIVE = "event_exclusive"
    DATE_INCLUSIVE = "date_inclusive"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CLOSED = "closed"
    ARCHIVED = "archived"


class TerminalReason(StrEnum):
    USER_COMPLETED = "user_completed"
    DEADLINE_REACHED = "deadline_reached"


class RouteStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    ADVANCED = "advanced"
    PAUSED = "paused"
    SUPERSEDED = "superseded"
    CLOSED = "closed"


class RouteClosureReason(StrEnum):
    PROJECT_COMPLETED = "project_completed"
    PROJECT_CLOSED = "project_closed"
    PROJECT_ARCHIVED = "project_archived"


@dataclass(slots=True)
class Project:
    id: UUID
    user_id: UUID
    name: str
    description: str
    goal_type: GoalType
    predecessor_project_id: UUID | None
    status: ProjectStatus
    target_date: date | None
    deadline_day_policy: DeadlineDayPolicy
    priority: int
    minimum_weekly_minutes: int
    confidence: Confidence
    route_revision: int
    plan_revision: int
    project_revision: int
    task_event_revision: int
    terminal_reason: TerminalReason | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentRouteNode:
    stage_id: UUID
    stage_title: str
    milestone_id: UUID
    milestone_title: str
    milestone_status: RouteStatus


@dataclass(frozen=True, slots=True)
class HistoryMilestone:
    id: UUID
    title: str
    stage_title: str
    status: RouteStatus
    transitioned_at: datetime | None


@dataclass(frozen=True, slots=True)
class FutureMilestone:
    id: UUID
    title: str
    stage_title: str
    status: RouteStatus
    target_week_start: date | None
    tentative: bool = True


@dataclass(frozen=True, slots=True)
class RouteView:
    project_id: UUID
    route_revision: int
    current: CurrentRouteNode | None
    history_milestones: tuple[HistoryMilestone, ...]
    future_milestones: tuple[FutureMilestone, ...]

    def validate_disjoint(self) -> None:
        groups: list[set[UUID]] = [
            {self.current.milestone_id} if self.current else set(),
            {item.id for item in self.history_milestones},
            {item.id for item in self.future_milestones},
        ]
        if any(groups[left] & groups[right] for left in range(3) for right in range(left + 1, 3)):
            raise ValueError("current, history and future route nodes must be disjoint")


@dataclass(frozen=True, slots=True)
class ClosureSnapshot:
    id: UUID
    project_id: UUID
    user_id: UUID
    closure_reason: TerminalReason
    target_date: date
    deadline_day_policy: DeadlineDayPolicy
    last_feasibility_status: str
    last_risk_detected_at: datetime | None
    completed_task_count: int
    unfinished_task_count: int
    completed_estimated_minutes: int
    completed_actual_minutes: int
    unfinished_estimated_minutes: int
    snapshot: dict[str, Any]
    created_at: datetime
