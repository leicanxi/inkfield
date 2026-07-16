from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.api.dependencies import get_session
from app.modules.identity.application.idempotency import IdempotencyService
from app.modules.identity.infrastructure.idempotency_repository import SqlIdempotencyRepository
from app.modules.planning.application.projects import NoopProjectLifecycleEffects, ProjectService
from app.modules.planning.infrastructure.repository import SqlProjectRepository


def get_project_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> ProjectService:
    return ProjectService(
        SqlProjectRepository(session), NoopProjectLifecycleEffects(), request.app.state.clock
    )


def get_idempotency_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> IdempotencyService:
    return IdempotencyService(SqlIdempotencyRepository(session), request.app.state.clock)
