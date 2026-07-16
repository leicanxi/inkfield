from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.identity.domain.entities import (
    AccessClaims,
    DevicePlatform,
    LoginSession,
    ProviderIdentity,
    RevokeReason,
    RotationResult,
    SessionSummary,
)


class WeChatIdentityProvider(Protocol):
    async def exchange_code(self, code: str) -> ProviderIdentity: ...


class IdentityRepository(Protocol):
    async def create_login_session(
        self,
        *,
        identity: ProviderIdentity,
        platform: DevicePlatform,
        device_label: str | None,
        fingerprint_hash: str | None,
        refresh_token_hash: str,
        now: datetime,
        refresh_expires_at: datetime,
    ) -> LoginSession: ...

    async def rotate_refresh_token(
        self,
        *,
        current_token_hash: str,
        successor_token_hash: str,
        now: datetime,
        successor_expires_at: datetime,
    ) -> RotationResult: ...

    async def validate_access_claims(self, claims: AccessClaims, now: datetime) -> bool: ...

    async def list_active_sessions(self, user_id: UUID, now: datetime) -> list[SessionSummary]: ...

    async def revoke_session(
        self, user_id: UUID, session_id: UUID, reason: RevokeReason, now: datetime
    ) -> bool: ...

    async def logout_all(self, user_id: UUID, now: datetime) -> None: ...
