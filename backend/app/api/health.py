from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.errors import DependencyUnavailableError
from app.core.observability import get_correlation_id
from app.core.schemas import HealthStatus, SuccessEnvelope

router = APIRouter(prefix="/health", tags=["operations"])


@router.get("/live", response_model=SuccessEnvelope[HealthStatus])
async def live(request: Request) -> SuccessEnvelope[HealthStatus]:
    return SuccessEnvelope(
        data=HealthStatus(status="ok", version=request.app.state.settings.app_version),
        correlation_id=get_correlation_id(),
    )


@router.get(
    "/ready",
    response_model=SuccessEnvelope[HealthStatus],
    responses={503: {"description": "A required dependency is unavailable"}},
)
async def ready(request: Request) -> SuccessEnvelope[HealthStatus]:
    checks: dict[str, str] = {}
    try:
        async with request.app.state.database_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["postgresql"] = "ok"
    except Exception as exc:
        raise DependencyUnavailableError("postgresql") from exc

    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        raise DependencyUnavailableError("redis") from exc

    return SuccessEnvelope(
        data=HealthStatus(
            status="ready",
            version=request.app.state.settings.app_version,
            dependencies=checks,
        ),
        correlation_id=get_correlation_id(),
    )
