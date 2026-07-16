from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


def create_database_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


@asynccontextmanager
async def transaction_scope(session: AsyncSession) -> AsyncIterator[None]:
    """Open a transaction unless the request already owns one."""
    if session.in_transaction():
        yield
        return
    async with session.begin():
        yield
