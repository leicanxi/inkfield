from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETING = "deleting"
    DELETED = "deleted"


class DevicePlatform(StrEnum):
    WECHAT_MINI = "wechat_mini"
    WEB = "web"
    IOS = "ios"
    ANDROID = "android"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class RefreshTokenStatus(StrEnum):
    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"
    REUSED = "reused"
    EXPIRED = "expired"


class RevokeReason(StrEnum):
    LOGOUT = "logout"
    DEVICE_REVOKED = "device_revoked"
    TOKEN_REUSE = "token_reuse"  # noqa: S105 - revoke reason, not a credential
    USER_DISABLED = "user_disabled"
    GLOBAL_LOGOUT = "global_logout"


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    provider: str
    subject: str
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    auth_version: int
    session_version: int
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LoginSession:
    user_id: UUID
    session_id: UUID
    auth_version: int
    session_version: int


@dataclass(frozen=True, slots=True)
class SessionSummary:
    session_id: UUID
    device_id: UUID
    platform: DevicePlatform
    device_label: str | None
    issued_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class RotationStatus(StrEnum):
    ROTATED = "rotated"
    REUSED = "reused"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class RotationResult:
    status: RotationStatus
    login_session: LoginSession | None = None
