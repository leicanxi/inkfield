from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.planning.domain.projects import (
    Confidence,
    DeadlineDayPolicy,
    GoalType,
    ProjectStatus,
    RouteStatus,
    TerminalReason,
)


class CreateProjectRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    goal_type: GoalType
    target_date: date | None = None
    deadline_day_policy: DeadlineDayPolicy = DeadlineDayPolicy.DATE_INCLUSIVE
    priority: int = Field(default=50, ge=1, le=100)
    minimum_weekly_minutes: int = Field(default=0, ge=0)
    predecessor_project_id: UUID | None = None


class RenameProjectRequest(ApiModel):
    expected_project_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)


class ProjectCommandRequest(ApiModel):
    expected_project_revision: int = Field(ge=1)


class CompleteProjectRequest(ProjectCommandRequest):
    completion_note: str | None = Field(default=None, max_length=2000)


class ProjectResponse(ApiModel):
    id: UUID
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


class CurrentStageResponse(ApiModel):
    id: UUID
    title: str


class CurrentMilestoneResponse(ApiModel):
    id: UUID
    title: str
    status: RouteStatus


class CurrentRouteResponse(ApiModel):
    stage: CurrentStageResponse
    milestone: CurrentMilestoneResponse


class HistoryMilestoneResponse(ApiModel):
    id: UUID
    title: str
    stage_title: str
    status: RouteStatus
    transitioned_at: datetime | None


class FutureMilestoneResponse(ApiModel):
    id: UUID
    title: str
    stage_title: str
    status: RouteStatus
    target_week_start: date | None
    tentative: bool


class RouteResponse(ApiModel):
    project_id: UUID
    route_revision: int
    current: CurrentRouteResponse | None
    history_milestones: list[HistoryMilestoneResponse]
    future_milestones: list[FutureMilestoneResponse]


class ClosureResponse(ApiModel):
    id: UUID
    project_id: UUID
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
