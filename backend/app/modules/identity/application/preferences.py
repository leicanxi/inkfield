from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.core.clock import Clock
from app.core.errors import AppError


@dataclass(frozen=True, slots=True)
class UserPreference:
    user_id: UUID
    weekly_capacity_minutes: int
    utilization_ratio: Decimal
    preferred_task_minutes: int
    max_task_minutes: int
    available_weekdays: int
    stable_preferences: dict[str, Any]
    preference_revision: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PreferenceUpdate:
    weekly_capacity_minutes: int
    utilization_ratio: Decimal
    preferred_task_minutes: int
    max_task_minutes: int
    available_weekdays: int
    stable_preferences: dict[str, Any]

    def validate(self) -> None:
        if self.weekly_capacity_minutes < 0:
            raise AppError("PREFERENCE_INVALID", "Weekly capacity cannot be negative.")
        if not Decimal("0") <= self.utilization_ratio <= Decimal("1"):
            raise AppError("PREFERENCE_INVALID", "Utilization ratio must be between 0 and 1.")
        if self.preferred_task_minutes <= 0:
            raise AppError("PREFERENCE_INVALID", "Preferred task duration must be positive.")
        if self.max_task_minutes < self.preferred_task_minutes:
            raise AppError(
                "PREFERENCE_INVALID",
                "Maximum task duration cannot be shorter than the preferred duration.",
            )
        if not 0 <= self.available_weekdays <= 127:
            raise AppError("PREFERENCE_INVALID", "Available weekdays must be a 7-bit mask.")


class PreferenceRepository(Protocol):
    async def get(self, user_id: UUID) -> UserPreference | None: ...

    async def update_if_revision(
        self,
        user_id: UUID,
        expected_revision: int,
        update_value: PreferenceUpdate,
        now: datetime,
    ) -> UserPreference | None: ...


class PreferenceService:
    def __init__(self, repository: PreferenceRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    async def get(self, user_id: UUID) -> UserPreference:
        preference = await self._repository.get(user_id)
        if preference is None:
            raise AppError("USER_NOT_FOUND", "User not found.", status_code=404)
        return preference

    async def update(
        self, user_id: UUID, expected_revision: int, update_value: PreferenceUpdate
    ) -> UserPreference:
        update_value.validate()
        updated = await self._repository.update_if_revision(
            user_id, expected_revision, update_value, self._clock.now()
        )
        if updated is None:
            raise AppError(
                "PREFERENCE_REVISION_CONFLICT",
                "Preferences changed; reload and try again.",
                status_code=409,
                details={"expected": expected_revision},
            )
        return updated
