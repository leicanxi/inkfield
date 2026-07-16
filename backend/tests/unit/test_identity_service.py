from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.modules.identity.application.service import AuthService
from app.modules.identity.application.tokens import AccessTokenCodec, hash_refresh_token
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

NOW = datetime(2026, 7, 16, 4, 0, tzinfo=UTC)


class FakeWeChatProvider:
    async def exchange_code(self, code: str) -> ProviderIdentity:
        return ProviderIdentity("wechat", f"subject:{code}", {"unionid": "not-sensitive"})


@dataclass(slots=True)
class FakeToken:
    session_id: UUID
    status: str


@dataclass(slots=True)
class FakeSession:
    login: LoginSession
    active: bool
    platform: DevicePlatform


class FakeIdentityRepository:
    def __init__(self) -> None:
        self.tokens: dict[str, FakeToken] = {}
        self.sessions_by_id: dict[UUID, FakeSession] = {}
        self._lock = asyncio.Lock()

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
        del device_label, fingerprint_hash, now, refresh_expires_at
        login = LoginSession(
            user_id=UUID(int=abs(hash(identity.subject)) % (2**128)),
            session_id=uuid4(),
            auth_version=1,
            session_version=1,
        )
        self.sessions_by_id[login.session_id] = FakeSession(login, True, platform)
        self.tokens[refresh_token_hash] = FakeToken(login.session_id, "active")
        return login

    async def rotate_refresh_token(
        self,
        *,
        current_token_hash: str,
        successor_token_hash: str,
        now: datetime,
        successor_expires_at: datetime,
    ) -> RotationResult:
        del now, successor_expires_at
        async with self._lock:
            token = self.tokens.get(current_token_hash)
            if token is None or token.status in {"revoked", "expired"}:
                return RotationResult(RotationStatus.INVALID)
            session = self.sessions_by_id[token.session_id]
            if token.status in {"rotated", "reused"}:
                token.status = "reused"
                session.active = False
                for candidate in self.tokens.values():
                    if candidate.session_id == session.login.session_id:
                        candidate.status = "revoked"
                return RotationResult(RotationStatus.REUSED)
            if not session.active:
                return RotationResult(RotationStatus.INVALID)
            token.status = "rotated"
            self.tokens[successor_token_hash] = FakeToken(token.session_id, "active")
            return RotationResult(RotationStatus.ROTATED, session.login)

    async def validate_access_claims(self, claims: AccessClaims, now: datetime) -> bool:
        session = self.sessions_by_id.get(claims.session_id)
        return bool(
            session
            and session.active
            and session.login.user_id == claims.user_id
            and session.login.auth_version == claims.auth_version
            and session.login.session_version == claims.session_version
            and claims.expires_at > now
        )

    async def list_active_sessions(self, user_id: UUID, now: datetime) -> list[SessionSummary]:
        del user_id, now
        return []

    async def revoke_session(
        self, user_id: UUID, session_id: UUID, reason: RevokeReason, now: datetime
    ) -> bool:
        del user_id, reason, now
        session = self.sessions_by_id.get(session_id)
        if session is None:
            return False
        session.active = False
        for token in self.tokens.values():
            if token.session_id == session_id:
                token.status = "revoked"
        return True

    async def logout_all(self, user_id: UUID, now: datetime) -> None:
        del now
        for session in self.sessions_by_id.values():
            if session.login.user_id == user_id:
                session.active = False


def make_service(repository: FakeIdentityRepository) -> AuthService:
    return AuthService(
        repository=repository,
        wechat_provider=FakeWeChatProvider(),
        token_codec=AccessTokenCodec("x" * 32, "test-issuer"),
        clock=FrozenClock(NOW),
        access_ttl_seconds=900,
        refresh_ttl_seconds=3600,
    )


@pytest.mark.asyncio
async def test_login_and_rotation_store_only_hashes() -> None:
    repository = FakeIdentityRepository()
    service = make_service(repository)

    first = await service.wechat_login(
        code="one",
        platform=DevicePlatform.WECHAT_MINI,
        device_label="phone",
        fingerprint_hash="a" * 64,
    )
    assert first.refresh_token not in repository.tokens
    assert hash_refresh_token(first.refresh_token) in repository.tokens

    second = await service.refresh(first.refresh_token)
    assert hash_refresh_token(first.refresh_token) in repository.tokens
    assert repository.tokens[hash_refresh_token(first.refresh_token)].status == "rotated"
    assert repository.tokens[hash_refresh_token(second.refresh_token)].status == "active"
    claims = await service.authenticate(second.access_token)
    assert claims.session_id in repository.sessions_by_id


@pytest.mark.asyncio
async def test_reusing_rotated_token_revokes_only_its_session() -> None:
    repository = FakeIdentityRepository()
    service = make_service(repository)
    first = await service.wechat_login(
        code="same-user",
        platform=DevicePlatform.WECHAT_MINI,
        device_label="first",
        fingerprint_hash="a" * 64,
    )
    other = await service.wechat_login(
        code="same-user",
        platform=DevicePlatform.WEB,
        device_label="second",
        fingerprint_hash="b" * 64,
    )
    successor = await service.refresh(first.refresh_token)

    with pytest.raises(AppError, match="reuse") as captured:
        await service.refresh(first.refresh_token)
    assert captured.value.code == "AUTH_REFRESH_TOKEN_REUSED"
    with pytest.raises(AppError) as invalidated:
        await service.authenticate(successor.access_token)
    assert invalidated.value.code == "AUTH_SESSION_INVALID"
    other_claims = await service.authenticate(other.access_token)
    assert repository.sessions_by_id[other_claims.session_id].active is True


@pytest.mark.asyncio
async def test_concurrent_refresh_creates_at_most_one_successor_then_revokes_session() -> None:
    repository = FakeIdentityRepository()
    service = make_service(repository)
    pair = await service.wechat_login(
        code="concurrent",
        platform=DevicePlatform.WECHAT_MINI,
        device_label=None,
        fingerprint_hash=None,
    )

    results = await asyncio.gather(
        service.refresh(pair.refresh_token),
        service.refresh(pair.refresh_token),
        return_exceptions=True,
    )
    successes = [result for result in results if not isinstance(result, BaseException)]
    failures = [result for result in results if isinstance(result, AppError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].code == "AUTH_REFRESH_TOKEN_REUSED"
    session_id = next(iter(repository.sessions_by_id))
    assert repository.sessions_by_id[session_id].active is False
    assert sum(token.status == "active" for token in repository.tokens.values()) == 0
