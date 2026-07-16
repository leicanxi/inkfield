from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.observability import CorrelationIdMiddleware, configure_logging
from app.infrastructure.database.session import create_database_engine
from app.infrastructure.redis import create_redis_client


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved
        app.state.database_engine = create_database_engine(resolved.database_url)
        app.state.redis = create_redis_client(resolved.redis_url)
        yield
        await app.state.redis.aclose()
        await app.state.database_engine.dispose()

    app = FastAPI(
        title="砚田日耕 API",
        version=resolved.app_version,
        lifespan=lifespan,
        docs_url="/docs" if resolved.app_env != "production" else None,
        redoc_url=None,
    )
    app.add_middleware(CorrelationIdMiddleware, header_name=resolved.correlation_header)
    register_exception_handlers(app)
    app.include_router(health_router)
    return app
