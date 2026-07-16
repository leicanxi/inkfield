from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.core.errors import AppError


class WeekPlanStatus(StrEnum):
    PREPARED = "prepared"
    ACTIVE = "active"
    SETTLED = "settled"
    SUPERSEDED = "superseded"


class WeekPlanCreationSource(StrEnum):
    INITIAL_PLANNING = "initial_planning"
    ALLOCATION_SHELL = "allocation_shell"
    WEEKLY_REVIEW = "weekly_review"
    TEMPORARY_REPLAN = "temporary_replan"
    RECOVERY = "recovery"
    CALIBRATION_HOLD = "calibration_hold"


@dataclass(frozen=True, slots=True)
class WeekPlanView:
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


class WeekPlanRepository(Protocol):
    async def get_project_weeks(
        self, user_id: UUID, project_id: UUID, week_start: date | None
    ) -> list[WeekPlanView]: ...


class WeekPlanService:
    def __init__(self, repository: WeekPlanRepository) -> None:
        self._repository = repository

    async def get_project_weeks(
        self, user_id: UUID, project_id: UUID, week_start: date | None = None
    ) -> list[WeekPlanView]:
        rows = await self._repository.get_project_weeks(user_id, project_id, week_start)
        if week_start is not None and not rows:
            raise AppError("WEEK_PLAN_NOT_FOUND", "Week plan not found.", status_code=404)
        return rows
