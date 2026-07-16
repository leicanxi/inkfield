from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.core.schemas import ApiModel
from app.modules.identity.domain.entities import DevicePlatform


class WeChatLoginRequest(ApiModel):
    code: str = Field(min_length=1, max_length=500)
    platform: DevicePlatform = DevicePlatform.WECHAT_MINI
    device_label: str | None = Field(default=None, max_length=100)
    fingerprint_hash: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("fingerprint_hash")
    @classmethod
    def fingerprint_must_be_hex(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                bytes.fromhex(value)
            except ValueError as exc:
                raise ValueError("fingerprint_hash must be hexadecimal") from exc
        return value


class RefreshRequest(ApiModel):
    refresh_token: str = Field(min_length=32, max_length=500)


class TokenPairResponse(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth scheme name, not a credential
    access_expires_in: int
    refresh_expires_in: int


class SessionResponse(ApiModel):
    session_id: UUID
    device_id: UUID
    platform: DevicePlatform
    device_label: str | None
    issued_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class PreferenceResponse(ApiModel):
    weekly_capacity_minutes: int
    utilization_ratio: Decimal
    preferred_task_minutes: int
    max_task_minutes: int
    available_weekdays: int
    stable_preferences: dict[str, Any]
    preference_revision: int
    updated_at: datetime


class MeResponse(ApiModel):
    user_id: UUID
    preferences: PreferenceResponse


class PreferenceUpdateRequest(ApiModel):
    expected_preference_revision: int = Field(ge=1)
    weekly_capacity_minutes: int = Field(ge=0)
    utilization_ratio: Decimal = Field(ge=0, le=1)
    preferred_task_minutes: int = Field(gt=0)
    max_task_minutes: int = Field(gt=0)
    available_weekdays: int = Field(ge=0, le=127)
    stable_preferences: dict[str, Any] = Field(default_factory=dict)

    @field_validator("max_task_minutes")
    @classmethod
    def max_duration_must_be_valid(cls, value: int, info: Any) -> int:
        preferred = info.data.get("preferred_task_minutes")
        if preferred is not None and value < preferred:
            raise ValueError("max_task_minutes must be >= preferred_task_minutes")
        return value
