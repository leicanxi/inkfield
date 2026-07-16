from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.modules.identity.application.idempotency import (
    ClaimStatus,
    IdempotencyClaim,
    IdempotencyRequest,
    IdempotencyService,
    canonical_request_hash,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)


@dataclass(slots=True)
class Record:
    request: IdempotencyRequest
    claim: IdempotencyClaim


class FakeIdempotencyRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[UUID, str], Record] = {}
        self._lock = asyncio.Lock()

    async def claim(
        self,
        request: IdempotencyRequest,
        now: datetime,
        locked_until: datetime,
        expires_at: datetime,
    ) -> IdempotencyClaim:
        del now, locked_until, expires_at
        async with self._lock:
            key = (request.user_id, request.key)
            existing = self.records.get(key)
            if existing is None:
                claim = IdempotencyClaim(ClaimStatus.ACQUIRED, uuid4())
                self.records[key] = Record(request, claim)
                return claim
            if (
                existing.request.method != request.method
                or existing.request.path != request.path
                or existing.request.request_hash != request.request_hash
            ):
                return IdempotencyClaim(ClaimStatus.REUSED, existing.claim.record_id)
            if existing.claim.status is ClaimStatus.REPLAY:
                return existing.claim
            return IdempotencyClaim(ClaimStatus.PROCESSING, existing.claim.record_id)

    async def complete(
        self,
        record_id: UUID,
        response_status: int,
        response_body: dict[str, Any],
        completed_at: datetime,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
    ) -> None:
        del completed_at, resource_type, resource_id
        for record in self.records.values():
            if record.claim.record_id == record_id:
                record.claim = IdempotencyClaim(
                    ClaimStatus.REPLAY, record_id, response_status, response_body
                )
                return
        raise AssertionError("record not found")


def request(user_id: UUID, body: dict[str, Any]) -> IdempotencyRequest:
    return IdempotencyRequest.create(
        user_id=user_id, key="same-key", method="post", path="//api/v1/projects/", body=body
    )


def test_canonical_hash_ignores_object_key_order() -> None:
    assert canonical_request_hash({"a": 1, "b": 2}) == canonical_request_hash({"b": 2, "a": 1})


@pytest.mark.asyncio
async def test_completed_request_replays_without_new_claim() -> None:
    repository = FakeIdempotencyRepository()
    service = IdempotencyService(repository, FrozenClock(NOW))
    original = request(uuid4(), {"name": "project"})
    claim = await service.claim(original)
    await service.complete(claim, 201, {"id": "p1"})

    replay = await service.claim(original)
    assert replay.status is ClaimStatus.REPLAY
    assert replay.response_status == 201
    assert replay.response_body == {"id": "p1"}


@pytest.mark.asyncio
async def test_same_user_key_with_different_body_is_rejected_but_other_user_is_independent() -> (
    None
):
    repository = FakeIdempotencyRepository()
    service = IdempotencyService(repository, FrozenClock(NOW))
    user_a, user_b = uuid4(), uuid4()
    await service.claim(request(user_a, {"value": 1}))
    with pytest.raises(AppError) as captured:
        await service.claim(request(user_a, {"value": 2}))
    assert captured.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert (await service.claim(request(user_b, {"value": 2}))).status is ClaimStatus.ACQUIRED
