from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import transaction_scope
from app.modules.identity.domain.entities import (
    AccessClaims,
    DevicePlatform,
    LoginSession,
    ProviderIdentity,
    RevokeReason,
    RotationResult,
    RotationStatus,
    SessionSummary,
)
from app.modules.identity.infrastructure.models import (
    AuthSessionModel,
    RefreshTokenModel,
    UserDeviceModel,
    UserIdentityModel,
    UserModel,
    UserPreferenceModel,
)


class SqlIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
    ) -> LoginSession:
        async with transaction_scope(self._session):
            identity_row = await self._session.scalar(
                select(UserIdentityModel)
                .where(
                    UserIdentityModel.provider == identity.provider,
                    UserIdentityModel.provider_subject == identity.subject,
                )
                .with_for_update()
            )
            if identity_row is None:
                user = UserModel(created_at=now, updated_at=now)
                self._session.add(user)
                await self._session.flush()
                identity_row = UserIdentityModel(
                    user_id=user.id,
                    provider=identity.provider,
                    provider_subject=identity.subject,
                    provider_metadata=identity.metadata,
                    created_at=now,
                    last_login_at=now,
                )
                self._session.add(identity_row)
                self._session.add(UserPreferenceModel(user_id=user.id, updated_at=now))
                await self._session.flush()
            else:
                existing_user = await self._session.get(
                    UserModel, identity_row.user_id, with_for_update=True
                )
                if existing_user is None or existing_user.status != "active":
                    raise ValueError("identity is bound to an inactive or missing user")
                user = existing_user
                identity_row.last_login_at = now
                identity_row.provider_metadata = identity.metadata

            device: UserDeviceModel | None = None
            if fingerprint_hash:
                device = await self._session.scalar(
                    select(UserDeviceModel)
                    .where(
                        UserDeviceModel.user_id == user.id,
                        UserDeviceModel.fingerprint_hash == fingerprint_hash,
                    )
                    .with_for_update()
                )
            if device is None:
                device = UserDeviceModel(
                    user_id=user.id,
                    platform=platform.value,
                    device_label=device_label,
                    fingerprint_hash=fingerprint_hash,
                    status="active",
                    last_seen_at=now,
                    created_at=now,
                )
                self._session.add(device)
                await self._session.flush()
            else:
                device.platform = platform.value
                device.device_label = device_label
                device.status = "active"
                device.revoked_at = None
                device.last_seen_at = now

            session = AuthSessionModel(
                user_id=user.id,
                identity_id=identity_row.id,
                device_id=device.id,
                auth_version_snapshot=user.auth_version,
                session_version=1,
                status="active",
                issued_at=now,
                last_seen_at=now,
                expires_at=refresh_expires_at,
            )
            self._session.add(session)
            await self._session.flush()
            self._session.add(
                RefreshTokenModel(
                    user_id=user.id,
                    session_id=session.id,
                    token_hash=refresh_token_hash,
                    status="active",
                    issued_at=now,
                    expires_at=refresh_expires_at,
                )
            )
            return LoginSession(
                user_id=user.id,
                session_id=session.id,
                auth_version=user.auth_version,
                session_version=session.session_version,
            )

    async def rotate_refresh_token(
        self,
        *,
        current_token_hash: str,
        successor_token_hash: str,
        now: datetime,
        successor_expires_at: datetime,
    ) -> RotationResult:
        async with transaction_scope(self._session):
            token = await self._session.scalar(
                select(RefreshTokenModel)
                .where(RefreshTokenModel.token_hash == current_token_hash)
                .with_for_update()
            )
            if token is None:
                return RotationResult(RotationStatus.INVALID)
            auth_session = await self._session.scalar(
                select(AuthSessionModel)
                .where(AuthSessionModel.id == token.session_id)
                .with_for_update()
            )
            if auth_session is None:
                return RotationResult(RotationStatus.INVALID)

            if token.status in {"rotated", "reused"}:
                token.status = "reused"
                token.used_at = now
                await self._revoke_locked_session(auth_session, RevokeReason.TOKEN_REUSE, now)
                return RotationResult(RotationStatus.REUSED)
            if token.status != "active":
                return RotationResult(RotationStatus.INVALID)
            if token.expires_at <= now:
                token.status = "expired"
                return RotationResult(RotationStatus.INVALID)
            if auth_session.status != "active" or auth_session.expires_at <= now:
                token.status = "revoked"
                token.revoked_at = now
                return RotationResult(RotationStatus.INVALID)

            user = await self._session.get(UserModel, token.user_id, with_for_update=True)
            if (
                user is None
                or user.status != "active"
                or user.auth_version != auth_session.auth_version_snapshot
            ):
                await self._revoke_locked_session(auth_session, RevokeReason.USER_DISABLED, now)
                return RotationResult(RotationStatus.INVALID)

            successor_id = uuid4()
            token.status = "rotated"
            token.used_at = now
            await self._session.flush()
            self._session.add(
                RefreshTokenModel(
                    id=successor_id,
                    user_id=token.user_id,
                    session_id=token.session_id,
                    token_hash=successor_token_hash,
                    parent_token_id=token.id,
                    status="active",
                    issued_at=now,
                    expires_at=successor_expires_at,
                )
            )
            await self._session.flush()
            token.replaced_by_token_id = successor_id
            auth_session.last_seen_at = now
            return RotationResult(
                RotationStatus.ROTATED,
                LoginSession(
                    user_id=user.id,
                    session_id=auth_session.id,
                    auth_version=user.auth_version,
                    session_version=auth_session.session_version,
                ),
            )

    async def validate_access_claims(self, claims: AccessClaims, now: datetime) -> bool:
        row = (
            await self._session.execute(
                select(UserModel.status, UserModel.auth_version, AuthSessionModel)
                .join(
                    AuthSessionModel,
                    (AuthSessionModel.user_id == UserModel.id)
                    & (AuthSessionModel.id == claims.session_id),
                )
                .where(UserModel.id == claims.user_id)
            )
        ).one_or_none()
        if row is None:
            return False
        user_status, auth_version, auth_session = row
        return bool(
            user_status == "active"
            and auth_version == claims.auth_version
            and auth_session.status == "active"
            and auth_session.session_version == claims.session_version
            and auth_session.auth_version_snapshot == claims.auth_version
            and auth_session.expires_at > now
            and claims.expires_at > now
        )

    async def list_active_sessions(self, user_id: UUID, now: datetime) -> list[SessionSummary]:
        rows = (
            await self._session.execute(
                select(AuthSessionModel, UserDeviceModel)
                .join(
                    UserDeviceModel,
                    (UserDeviceModel.id == AuthSessionModel.device_id)
                    & (UserDeviceModel.user_id == AuthSessionModel.user_id),
                )
                .where(
                    AuthSessionModel.user_id == user_id,
                    AuthSessionModel.status == "active",
                    AuthSessionModel.expires_at > now,
                )
                .order_by(AuthSessionModel.last_seen_at.desc())
            )
        ).all()
        return [
            SessionSummary(
                session_id=session.id,
                device_id=device.id,
                platform=DevicePlatform(device.platform),
                device_label=device.device_label,
                issued_at=session.issued_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
            )
            for session, device in rows
        ]

    async def revoke_session(
        self, user_id: UUID, session_id: UUID, reason: RevokeReason, now: datetime
    ) -> bool:
        async with transaction_scope(self._session):
            auth_session = await self._session.scalar(
                select(AuthSessionModel)
                .where(AuthSessionModel.id == session_id, AuthSessionModel.user_id == user_id)
                .with_for_update()
            )
            if auth_session is None:
                return False
            await self._revoke_locked_session(auth_session, reason, now)
            return True

    async def logout_all(self, user_id: UUID, now: datetime) -> None:
        async with transaction_scope(self._session):
            user = await self._session.get(UserModel, user_id, with_for_update=True)
            if user is None:
                return
            user.auth_version += 1
            user.updated_at = now
            await self._session.execute(
                update(AuthSessionModel)
                .where(AuthSessionModel.user_id == user_id, AuthSessionModel.status == "active")
                .values(
                    status="revoked",
                    revoked_at=now,
                    revoke_reason=RevokeReason.GLOBAL_LOGOUT.value,
                )
            )
            await self._session.execute(
                update(RefreshTokenModel)
                .where(
                    RefreshTokenModel.user_id == user_id,
                    RefreshTokenModel.status == "active",
                )
                .values(status="revoked", revoked_at=now)
            )

    async def _revoke_locked_session(
        self, auth_session: AuthSessionModel, reason: RevokeReason, now: datetime
    ) -> None:
        auth_session.status = "revoked"
        auth_session.session_version += 1
        auth_session.revoked_at = now
        auth_session.revoke_reason = reason.value
        await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.session_id == auth_session.id,
                RefreshTokenModel.status == "active",
            )
            .values(status="revoked", revoked_at=now)
        )
