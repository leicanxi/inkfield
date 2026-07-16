from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from app.core.schemas import ApiModel
from app.modules.planning.application.week_plans import (
    WeekPlanCreationSource,
    WeekPlanStatus,
)
from app.modules.planning.domain.capacity import (
    AllocationReason,
    AllocationStatus,
    CapacityStatus,
    DeadlineRisk,
)


class AllocationResponse(ApiModel):
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


class UserWeekResponse(ApiModel):
    capacity_id: UUID
    week_start: date
    total_minutes: int
    allocatable_minutes: int
    buffer_minutes: int
    allocated_minutes: int
    planned_minutes: int
    actual_minutes: int
    status: CapacityStatus
    active_allocation_revision: int
    allocations: list[AllocationResponse]
    updated_at: datetime


class WeekPlanResponse(ApiModel):
    id: UUID
    project_id: UUID
    allocation_id: UUID
    week_start: date
    status: WeekPlanStatus
    generation: int
    version: int
    project_plan_revision: int
    budget_minutes: int
    planned_minutes: int
    summary: str
    creation_source: WeekPlanCreationSource
    promoted_at: datetime | None
    settled_at: datetime | None
