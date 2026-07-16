from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.tasks.domain.task_events import (
    Necessity,
    TaskEventType,
    TaskKind,
    TaskStatus,
)


class TaskEventRequest(ApiModel):
    event_type: TaskEventType
    expected_task_version: int = Field(ge=1)
    actual_minutes: int | None = Field(default=None, ge=0)
    reason_code: str | None = Field(default=None, max_length=40)
    note: str | None = None
    occurred_at: datetime


class TaskEventResponse(ApiModel):
    id: UUID
    task_id: UUID
    project_id: UUID
    project_event_revision: int
    event_type: TaskEventType
    previous_status: TaskStatus
    new_status: TaskStatus
    actual_minutes: int | None
    reason_code: str | None
    note: str | None
    occurred_at: datetime
    created_at: datetime
    task_version: int


class TaskResponse(ApiModel):
    id: UUID
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
    is_blocking: bool
    is_blocked: bool
    unmet_prerequisites: list[UUID]
