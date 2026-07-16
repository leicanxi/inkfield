from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.identity.application.preferences import PreferenceService
from app.modules.identity.application.service import AuthService
from app.modules.identity.application.tokens import AccessTokenCodec
from app.modules.identity.domain.entities import AccessClaims
from app.modules.identity.infrastructure.preferences_repository import SqlPreferenceRepository
from app.modules.identity.infrastructure.repository import SqlIdentityRepository

bearer = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()


def get_auth_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AuthService:
    settings = request.app.state.settings
    return AuthService(
        repository=SqlIdentityRepository(session),
        wechat_provider=request.app.state.wechat_provider,
        token_codec=AccessTokenCodec(
            settings.token_signing_key.get_secret_value(), settings.token_issuer
        ),
        clock=request.app.state.clock,
        access_ttl_seconds=settings.access_token_ttl_seconds,
        refresh_ttl_seconds=settings.refresh_token_ttl_seconds,
    )


def get_preference_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> PreferenceService:
    return PreferenceService(SqlPreferenceRepository(session), request.app.state.clock)


async def current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AccessClaims:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    return await service.authenticate(credentials.credentials)
