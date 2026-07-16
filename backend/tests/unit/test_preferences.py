from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.modules.identity.application.preferences import (
    PreferenceService,
    PreferenceUpdate,
    UserPreference,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)


class FakePreferenceRepository:
    def __init__(self, preference: UserPreference) -> None:
        self.preference = preference
        self._lock = asyncio.Lock()

    async def get(self, user_id: UUID) -> UserPreference | None:
        return self.preference if self.preference.user_id == user_id else None

    async def update_if_revision(
        self,
        user_id: UUID,
        expected_revision: int,
        update_value: PreferenceUpdate,
        now: datetime,
    ) -> UserPreference | None:
        async with self._lock:
            if self.preference.user_id != user_id:
                return None
            if self.preference.preference_revision != expected_revision:
                return None
            self.preference = UserPreference(
                user_id=user_id,
                weekly_capacity_minutes=update_value.weekly_capacity_minutes,
                utilization_ratio=update_value.utilization_ratio,
                preferred_task_minutes=update_value.preferred_task_minutes,
                max_task_minutes=update_value.max_task_minutes,
                available_weekdays=update_value.available_weekdays,
                stable_preferences=update_value.stable_preferences,
                preference_revision=expected_revision + 1,
                updated_at=now,
            )
            return self.preference


def update(capacity: int) -> PreferenceUpdate:
    return PreferenceUpdate(capacity, Decimal("0.85"), 30, 90, 31, {})


@pytest.mark.asyncio
async def test_preference_update_uses_revision_cas() -> None:
    user_id = uuid4()
    repository = FakePreferenceRepository(
        UserPreference(user_id, 300, Decimal("0.85"), 30, 90, 31, {}, 1, NOW)
    )
    service = PreferenceService(repository, FrozenClock(NOW))
    changed = await service.update(user_id, 1, update(480))
    assert changed.preference_revision == 2
    assert changed.weekly_capacity_minutes == 480

    with pytest.raises(AppError) as captured:
        await service.update(user_id, 1, update(600))
    assert captured.value.code == "PREFERENCE_REVISION_CONFLICT"


@pytest.mark.asyncio
async def test_concurrent_preference_updates_allow_exactly_one_writer() -> None:
    user_id = uuid4()
    repository = FakePreferenceRepository(
        UserPreference(user_id, 300, Decimal("0.85"), 30, 90, 31, {}, 5, NOW)
    )
    service = PreferenceService(repository, FrozenClock(NOW))
    results = await asyncio.gather(
        service.update(user_id, 5, update(400)),
        service.update(user_id, 5, update(500)),
        return_exceptions=True,
    )
    assert sum(isinstance(result, UserPreference) for result in results) == 1
    errors = [result for result in results if isinstance(result, AppError)]
    assert len(errors) == 1 and errors[0].code == "PREFERENCE_REVISION_CONFLICT"
    assert repository.preference.preference_revision == 6
