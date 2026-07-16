from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from app.core.clock import Clock
from app.core.errors import AppError


def canonical_request_hash(body: Any) -> str:
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_request_path(path: str) -> str:
    normalized = "/" + "/".join(segment for segment in path.strip().split("/") if segment)
    return normalized or "/"


@dataclass(frozen=True, slots=True)
class IdempotencyRequest:
    user_id: UUID
    key: str
    method: str
    path: str
    request_hash: str

    @classmethod
    def create(
        cls, *, user_id: UUID, key: str, method: str, path: str, body: Any
    ) -> IdempotencyRequest:
        cleaned_key = key.strip()
        if not cleaned_key or len(cleaned_key) > 200:
            raise AppError(
                "IDEMPOTENCY_KEY_INVALID",
                "Idempotency-Key must contain between 1 and 200 characters.",
                status_code=400,
            )
        return cls(
            user_id=user_id,
            key=cleaned_key,
            method=method.upper(),
            path=normalize_request_path(path),
            request_hash=canonical_request_hash(body),
        )


class ClaimStatus(StrEnum):
    ACQUIRED = "acquired"
    REPLAY = "replay"
    PROCESSING = "processing"
    REUSED = "reused"


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    status: ClaimStatus
    record_id: UUID
    response_status: int | None = None
    response_body: dict[str, Any] | None = None


class IdempotencyRepository(Protocol):
    async def claim(
        self,
        request: IdempotencyRequest,
        now: datetime,
        locked_until: datetime,
        expires_at: datetime,
    ) -> IdempotencyClaim: ...

    async def complete(
        self,
        record_id: UUID,
        response_status: int,
        response_body: dict[str, Any],
        completed_at: datetime,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
    ) -> None: ...


class IdempotencyService:
    def __init__(
        self,
        repository: IdempotencyRepository,
        clock: Clock,
        *,
        lease_seconds: int = 30,
        retention_seconds: int = 86_400,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._lease = lease_seconds
        self._retention = retention_seconds

    async def claim(self, request: IdempotencyRequest) -> IdempotencyClaim:
        now = self._clock.now()
        claim = await self._repository.claim(
            request,
            now,
            now + timedelta(seconds=self._lease),
            now + timedelta(seconds=self._retention),
        )
        if claim.status is ClaimStatus.REUSED:
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was already used for a different request.",
                status_code=409,
            )
        if claim.status is ClaimStatus.PROCESSING:
            raise AppError(
                "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                "The original request is still being processed.",
                status_code=409,
                retryable=True,
            )
        return claim

    async def complete(
        self,
        claim: IdempotencyClaim,
        response_status: int,
        response_body: dict[str, Any],
        *,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
    ) -> None:
        if claim.status is not ClaimStatus.ACQUIRED:
            return
        await self._repository.complete(
            claim.record_id,
            response_status,
            response_body,
            self._clock.now(),
            resource_type,
            resource_id,
        )
