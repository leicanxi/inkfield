from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.core.clock import Clock
from app.core.errors import AppError
from app.modules.planning.domain.capacity import (
    AllocationSetReason,
    UserWeekRunStatus,
    UserWeekRunType,
    UserWeekSummary,
    validate_week_start,
)


@dataclass(frozen=True, slots=True)
class CapacityInput:
    week_start: date
    total_minutes: int
    allocatable_minutes: int
    buffer_minutes: int
    preference_revision: int

    def validate(self) -> None:
        validate_week_start(self.week_start)
        if (
            min(
                self.total_minutes,
                self.allocatable_minutes,
                self.buffer_minutes,
                self.preference_revision,
            )
            < 0
        ):
            raise AppError("CAPACITY_INVALID", "Capacity values cannot be negative.")
        if self.preference_revision < 1:
            raise AppError("CAPACITY_INVALID", "preference_revision must be positive.")
        if self.allocatable_minutes + self.buffer_minutes > self.total_minutes:
            raise AppError(
                "CAPACITY_INVALID", "Allocatable capacity and buffer exceed total capacity."
            )


@dataclass(frozen=True, slots=True)
class ReallocationCommand:
    week_start: date
    desired_minutes: dict[UUID, int]
    reason: AllocationSetReason
    source_run_id: UUID | None
    prepared: bool


@dataclass(frozen=True, slots=True)
class UserWeekRunView:
    id: UUID
    user_id: UUID
    week_start: date
    run_type: UserWeekRunType
    status: UserWeekRunStatus
    idempotency_key: str


class CapacityRepository(Protocol):
    async def ensure_capacity(
        self, user_id: UUID, value: CapacityInput, now: datetime
    ) -> UserWeekSummary: ...

    async def create_run(
        self,
        user_id: UUID,
        week_start: date,
        run_type: UserWeekRunType,
        trigger_ref: str | None,
        idempotency_key: str,
        now: datetime,
    ) -> UserWeekRunView: ...

    async def reallocate(
        self, user_id: UUID, command: ReallocationCommand, now: datetime
    ) -> UserWeekSummary: ...

    async def get_summary(self, user_id: UUID, week_start: date) -> UserWeekSummary | None: ...


class CapacityService:
    def __init__(self, repository: CapacityRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    async def ensure_capacity(self, user_id: UUID, value: CapacityInput) -> UserWeekSummary:
        value.validate()
        return await self._repository.ensure_capacity(user_id, value, self._clock.now())

    async def create_run(
        self,
        user_id: UUID,
        week_start: date,
        run_type: UserWeekRunType,
        trigger_ref: str | None,
        idempotency_key: str,
    ) -> UserWeekRunView:
        validate_week_start(week_start)
        if not idempotency_key.strip() or len(idempotency_key) > 200:
            raise AppError("IDEMPOTENCY_KEY_INVALID", "Invalid user-week run idempotency key.")
        return await self._repository.create_run(
            user_id,
            week_start,
            run_type,
            trigger_ref,
            idempotency_key,
            self._clock.now(),
        )

    async def reallocate(self, user_id: UUID, command: ReallocationCommand) -> UserWeekSummary:
        validate_week_start(command.week_start)
        if any(value < 0 for value in command.desired_minutes.values()):
            raise AppError("ALLOCATION_INPUT_INVALID", "Desired minutes cannot be negative.")
        return await self._repository.reallocate(user_id, command, self._clock.now())

    async def get(self, user_id: UUID, week_start: date) -> UserWeekSummary:
        validate_week_start(week_start)
        result = await self._repository.get_summary(user_id, week_start)
        if result is None:
            raise AppError("USER_WEEK_NOT_FOUND", "User week not found.", status_code=404)
        return result
