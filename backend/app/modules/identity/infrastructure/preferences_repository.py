from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import transaction_scope
from app.modules.identity.application.preferences import (
    PreferenceUpdate,
    UserPreference,
)
from app.modules.identity.infrastructure.models import UserPreferenceModel


def _to_domain(row: UserPreferenceModel) -> UserPreference:
    return UserPreference(
        user_id=row.user_id,
        weekly_capacity_minutes=row.weekly_capacity_minutes,
        utilization_ratio=row.utilization_ratio,
        preferred_task_minutes=row.preferred_task_minutes,
        max_task_minutes=row.max_task_minutes,
        available_weekdays=row.available_weekdays,
        stable_preferences=row.stable_preferences,
        preference_revision=row.preference_revision,
        updated_at=row.updated_at,
    )


class SqlPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> UserPreference | None:
        row = await self._session.get(UserPreferenceModel, user_id)
        return _to_domain(row) if row else None

    async def update_if_revision(
        self,
        user_id: UUID,
        expected_revision: int,
        update_value: PreferenceUpdate,
        now: datetime,
    ) -> UserPreference | None:
        async with transaction_scope(self._session):
            result = await self._session.execute(
                update(UserPreferenceModel)
                .where(
                    UserPreferenceModel.user_id == user_id,
                    UserPreferenceModel.preference_revision == expected_revision,
                )
                .values(
                    weekly_capacity_minutes=update_value.weekly_capacity_minutes,
                    utilization_ratio=update_value.utilization_ratio,
                    preferred_task_minutes=update_value.preferred_task_minutes,
                    max_task_minutes=update_value.max_task_minutes,
                    available_weekdays=update_value.available_weekdays,
                    stable_preferences=update_value.stable_preferences,
                    preference_revision=UserPreferenceModel.preference_revision + 1,
                    updated_at=now,
                )
                .returning(UserPreferenceModel)
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row else None
