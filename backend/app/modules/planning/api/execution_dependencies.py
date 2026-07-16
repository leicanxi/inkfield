from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.api.dependencies import get_session
from app.modules.planning.application.capacity import CapacityService
from app.modules.planning.application.week_plans import WeekPlanService
from app.modules.planning.infrastructure.capacity_repository import SqlCapacityRepository
from app.modules.planning.infrastructure.week_plan_repository import SqlWeekPlanRepository
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.infrastructure.repository import SqlTaskRepository


def get_capacity_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> CapacityService:
    return CapacityService(SqlCapacityRepository(session), request.app.state.clock)


def get_week_plan_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WeekPlanService:
    return WeekPlanService(SqlWeekPlanRepository(session))


def get_task_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> TaskService:
    return TaskService(SqlTaskRepository(session), request.app.state.clock)
