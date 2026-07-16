from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.core.clock import Clock
from app.core.errors import AppError
from app.modules.tasks.domain.task_events import (
    Necessity,
    Task,
    TaskEventCommand,
    TaskEventType,
    TaskStatus,
)


@dataclass(frozen=True, slots=True)
class TaskEventView:
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


@dataclass(frozen=True, slots=True)
class TaskQueryItem:
    task: Task
    is_blocking: bool
    is_blocked: bool
    unmet_prerequisites: tuple[UUID, ...]


class TaskRepository(Protocol):
    async def append_event(
        self,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        command: TaskEventCommand,
        received_at: datetime,
    ) -> TaskEventView: ...

    async def get(self, user_id: UUID, task_id: UUID) -> TaskQueryItem | None: ...

    async def query(
        self,
        user_id: UUID,
        *,
        week_start: date | None,
        project_id: UUID | None,
        statuses: tuple[TaskStatus, ...],
        necessity: Necessity | None,
        due_before: date | None,
    ) -> list[TaskQueryItem]: ...


class TaskService:
    def __init__(self, repository: TaskRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    async def append_event(
        self,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        command: TaskEventCommand,
    ) -> TaskEventView:
        if not idempotency_key.strip() or len(idempotency_key) > 200:
            raise AppError("IDEMPOTENCY_KEY_INVALID", "Invalid task event idempotency key.")
        return await self._repository.append_event(
            user_id, task_id, idempotency_key, command, self._clock.now()
        )

    async def get(self, user_id: UUID, task_id: UUID) -> TaskQueryItem:
        result = await self._repository.get(user_id, task_id)
        if result is None:
            raise AppError("TASK_NOT_FOUND", "Task not found.", status_code=404)
        return result

    async def query(
        self,
        user_id: UUID,
        *,
        week_start: date | None = None,
        project_id: UUID | None = None,
        statuses: tuple[TaskStatus, ...] = (),
        necessity: Necessity | None = None,
        due_before: date | None = None,
    ) -> list[TaskQueryItem]:
        return await self._repository.query(
            user_id,
            week_start=week_start,
            project_id=project_id,
            statuses=statuses,
            necessity=necessity,
            due_before=due_before,
        )
