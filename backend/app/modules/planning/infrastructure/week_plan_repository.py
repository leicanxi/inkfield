from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.application.week_plans import (
    WeekPlanCreationSource,
    WeekPlanStatus,
    WeekPlanView,
)
from app.modules.planning.infrastructure.execution_models import WeekPlanModel


class SqlWeekPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_project_weeks(
        self, user_id: UUID, project_id: UUID, week_start: date | None
    ) -> list[WeekPlanView]:
        statement = select(WeekPlanModel).where(
            WeekPlanModel.user_id == user_id,
            WeekPlanModel.project_id == project_id,
        )
        if week_start is None:
            statement = statement.where(WeekPlanModel.status.in_(["active", "prepared"]))
        else:
            statement = statement.where(WeekPlanModel.week_start == week_start)
        rows = list(
            (
                await self._session.scalars(
                    statement.order_by(WeekPlanModel.week_start, WeekPlanModel.generation.desc())
                )
            ).all()
        )
        return [
            WeekPlanView(
                row.id,
                row.project_id,
                row.allocation_id,
                row.week_start,
                WeekPlanStatus(row.status),
                row.generation,
                row.version,
                row.project_plan_revision,
                row.budget_minutes,
                row.planned_minutes,
                row.summary,
                WeekPlanCreationSource(row.creation_source),
                row.promoted_at,
                row.settled_at,
            )
            for row in rows
        ]
