from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import transaction_scope
from app.modules.identity.application.idempotency import (
    ClaimStatus,
    IdempotencyClaim,
    IdempotencyRequest,
)
from app.modules.identity.infrastructure.models import ApiIdempotencyRecordModel


class SqlIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        request: IdempotencyRequest,
        now: datetime,
        locked_until: datetime,
        expires_at: datetime,
    ) -> IdempotencyClaim:
        async with transaction_scope(self._session):
            candidate_id = uuid4()
            inserted_id = await self._session.scalar(
                insert(ApiIdempotencyRecordModel)
                .values(
                    id=candidate_id,
                    user_id=request.user_id,
                    idempotency_key=request.key,
                    request_method=request.method,
                    request_path=request.path,
                    request_hash=request.request_hash,
                    status="processing",
                    locked_until=locked_until,
                    expires_at=expires_at,
                    created_at=now,
                )
                .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
                .returning(ApiIdempotencyRecordModel.id)
            )
            if inserted_id is not None:
                return IdempotencyClaim(ClaimStatus.ACQUIRED, inserted_id)

            record = await self._session.scalar(
                select(ApiIdempotencyRecordModel)
                .where(
                    ApiIdempotencyRecordModel.user_id == request.user_id,
                    ApiIdempotencyRecordModel.idempotency_key == request.key,
                )
                .with_for_update()
            )
            if record is None:
                raise RuntimeError("idempotency conflict row disappeared")
            if (
                record.request_method != request.method
                or record.request_path != request.path
                or record.request_hash != request.request_hash
            ):
                return IdempotencyClaim(ClaimStatus.REUSED, record.id)
            if record.status == "completed":
                return IdempotencyClaim(
                    ClaimStatus.REPLAY,
                    record.id,
                    record.response_status,
                    record.response_body,
                )
            if record.status == "processing" and record.locked_until and record.locked_until > now:
                return IdempotencyClaim(ClaimStatus.PROCESSING, record.id)

            record.status = "processing"
            record.locked_until = locked_until
            record.expires_at = expires_at
            return IdempotencyClaim(ClaimStatus.ACQUIRED, record.id)

    async def complete(
        self,
        record_id: UUID,
        response_status: int,
        response_body: dict[str, Any],
        completed_at: datetime,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
    ) -> None:
        async with transaction_scope(self._session):
            await self._session.execute(
                update(ApiIdempotencyRecordModel)
                .where(
                    ApiIdempotencyRecordModel.id == record_id,
                    ApiIdempotencyRecordModel.status == "processing",
                )
                .values(
                    status="completed",
                    response_status=response_status,
                    response_body=response_body,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    locked_until=None,
                    completed_at=completed_at,
                )
            )
