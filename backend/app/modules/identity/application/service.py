from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from app.core.clock import Clock
from app.core.errors import AppError
from app.modules.identity.application.ports import IdentityRepository, WeChatIdentityProvider
from app.modules.identity.application.tokens import (
    AccessTokenCodec,
    generate_refresh_token,
    hash_refresh_token,
)
from app.modules.identity.domain.entities import (
    AccessClaims,
    DevicePlatform,
    LoginSession,
    RevokeReason,
    RotationStatus,
    SessionSummary,
)


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int


class AuthService:
    def __init__(
        self,
        *,
        repository: IdentityRepository,
        wechat_provider: WeChatIdentityProvider,
        token_codec: AccessTokenCodec,
        clock: Clock,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
    ) -> None:
        self._repository = repository
        self._wechat_provider = wechat_provider
        self._token_codec = token_codec
        self._clock = clock
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds

    def _issue_pair(self, login: LoginSession, raw_refresh: str) -> TokenPair:
        now = self._clock.now()
        access_expires_at = now + timedelta(seconds=self._access_ttl)
        return TokenPair(
            access_token=self._token_codec.encode(login, now, access_expires_at),
            refresh_token=raw_refresh,
            access_expires_in=self._access_ttl,
            refresh_expires_in=self._refresh_ttl,
        )

    async def wechat_login(
        self,
        *,
        code: str,
        platform: DevicePlatform,
        device_label: str | None,
        fingerprint_hash: str | None,
    ) -> TokenPair:
        identity = await self._wechat_provider.exchange_code(code)
        if identity.provider != "wechat":
            raise AppError("AUTH_PROVIDER_INVALID", "Identity provider mismatch.", status_code=401)
        raw_refresh = generate_refresh_token()
        now = self._clock.now()
        login = await self._repository.create_login_session(
            identity=identity,
            platform=platform,
            device_label=device_label,
            fingerprint_hash=fingerprint_hash,
            refresh_token_hash=hash_refresh_token(raw_refresh),
            now=now,
            refresh_expires_at=now + timedelta(seconds=self._refresh_ttl),
        )
        return self._issue_pair(login, raw_refresh)

    async def refresh(self, raw_refresh: str) -> TokenPair:
        successor = generate_refresh_token()
        now = self._clock.now()
        result = await self._repository.rotate_refresh_token(
            current_token_hash=hash_refresh_token(raw_refresh),
            successor_token_hash=hash_refresh_token(successor),
            now=now,
            successor_expires_at=now + timedelta(seconds=self._refresh_ttl),
        )
        if result.status is RotationStatus.REUSED:
            raise AppError(
                "AUTH_REFRESH_TOKEN_REUSED",
                "Refresh token reuse was detected; the session was revoked.",
                status_code=401,
            )
        if result.status is RotationStatus.INVALID or result.login_session is None:
            raise AppError(
                "AUTH_REFRESH_TOKEN_INVALID",
                "The refresh token is invalid or expired.",
                status_code=401,
            )
        return self._issue_pair(result.login_session, successor)

    async def authenticate(self, raw_access: str) -> AccessClaims:
        claims = self._token_codec.decode(raw_access)
        if not await self._repository.validate_access_claims(claims, self._clock.now()):
            raise AppError(
                "AUTH_SESSION_INVALID",
                "The session is no longer active.",
                status_code=401,
            )
        return claims

    async def sessions(self, user_id: UUID) -> list[SessionSummary]:
        return await self._repository.list_active_sessions(user_id, self._clock.now())

    async def logout(self, claims: AccessClaims) -> None:
        await self._repository.revoke_session(
            claims.user_id, claims.session_id, RevokeReason.LOGOUT, self._clock.now()
        )

    async def revoke_session(self, claims: AccessClaims, session_id: UUID) -> None:
        found = await self._repository.revoke_session(
            claims.user_id, session_id, RevokeReason.DEVICE_REVOKED, self._clock.now()
        )
        if not found:
            raise AppError("AUTH_SESSION_NOT_FOUND", "Session not found.", status_code=404)

    async def logout_all(self, claims: AccessClaims) -> None:
        await self._repository.logout_all(claims.user_id, self._clock.now())
