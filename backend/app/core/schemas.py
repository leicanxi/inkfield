from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SuccessEnvelope(ApiModel, Generic[T]):
    data: T
    correlation_id: str


class ErrorBody(ApiModel):
    code: str
    message: str
    retryable: bool = False
    correlation_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(ApiModel):
    error: ErrorBody


class HealthStatus(ApiModel):
    status: str
    version: str
    dependencies: dict[str, str] = Field(default_factory=dict)
