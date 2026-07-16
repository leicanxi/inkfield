from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'deleting', 'deleted')",
            name="status_values",
        ),
        Index("ix_users_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="zh-CN")
    auth_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserIdentityModel(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject"),
        UniqueConstraint("id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserDeviceModel(Base):
    __tablename__ = "user_devices"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('wechat_mini', 'web', 'ios', 'android')",
            name="platform_values",
        ),
        CheckConstraint("status IN ('active', 'revoked')", name="status_values"),
        CheckConstraint(
            "fingerprint_hash IS NULL OR length(fingerprint_hash) = 64",
            name="fingerprint_hash_length",
        ),
        UniqueConstraint("id", "user_id"),
        Index(
            "uq_user_devices_user_fingerprint_active",
            "user_id",
            "fingerprint_hash",
            unique=True,
            postgresql_where=text("fingerprint_hash IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    device_label: Mapped[str | None] = mapped_column(String(100))
    fingerprint_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSessionModel(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked', 'expired')", name="status_values"),
        CheckConstraint(
            "revoke_reason IS NULL OR revoke_reason IN "
            "('logout', 'device_revoked', 'token_reuse', 'user_disabled', 'global_logout')",
            name="revoke_reason_values",
        ),
        ForeignKeyConstraint(
            ["identity_id", "user_id"],
            ["user_identities.id", "user_identities.user_id"],
        ),
        ForeignKeyConstraint(["device_id", "user_id"], ["user_devices.id", "user_devices.user_id"]),
        UniqueConstraint("id", "user_id"),
        Index("ix_auth_sessions_user_status", "user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    identity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    device_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    auth_version_snapshot: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(30))


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'rotated', 'revoked', 'reused', 'expired')",
            name="status_values",
        ),
        CheckConstraint("length(token_hash) = 64", name="token_hash_length"),
        ForeignKeyConstraint(
            ["session_id", "user_id"], ["auth_sessions.id", "auth_sessions.user_id"]
        ),
        Index(
            "uq_refresh_tokens_one_active_per_session",
            "session_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    parent_token_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("refresh_tokens.id")
    )
    replaced_by_token_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("refresh_tokens.id")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserPreferenceModel(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("weekly_capacity_minutes >= 0", name="weekly_capacity_nonnegative"),
        CheckConstraint(
            "utilization_ratio >= 0 AND utilization_ratio <= 1",
            name="utilization_ratio_range",
        ),
        CheckConstraint("preferred_task_minutes > 0", name="preferred_task_positive"),
        CheckConstraint("max_task_minutes >= preferred_task_minutes", name="max_task_not_smaller"),
        CheckConstraint(
            "available_weekdays >= 0 AND available_weekdays <= 127",
            name="available_weekdays_mask",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    weekly_capacity_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    utilization_ratio: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("0.850")
    )
    preferred_task_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    max_task_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    available_weekdays: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=127)
    stable_preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    preference_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApiIdempotencyRecordModel(Base):
    __tablename__ = "api_idempotency_records"
    __table_args__ = (
        CheckConstraint("status IN ('processing', 'completed', 'failed')", name="status_values"),
        CheckConstraint("length(request_hash) = 64", name="request_hash_length"),
        UniqueConstraint("user_id", "idempotency_key"),
        Index("ix_api_idempotency_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_method: Mapped[str] = mapped_column(String(10), nullable=False)
    request_path: Mapped[str] = mapped_column(String(500), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
