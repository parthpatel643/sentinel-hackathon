"""Async SQLAlchemy engine and session factory.

One engine per process, created lazily so importing this module never
requires a live database (important for unit tests that only need the ORM
models' shape, not a connection).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from sentinel_core.config import get_settings

__all__ = ["Base", "get_engine", "get_session", "get_sessionmaker"]


class Base(DeclarativeBase):
    """Every ORM model in core_api inherits from this."""


def _asyncpg_url(database_url: str) -> str:
    """SQLAlchemy's async engine needs the `+asyncpg` driver suffix; Settings
    exposes a plain `postgresql://` DSN shared with anything else that might
    want it (psql, other tooling), so the suffix is added here, once."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    # pool_pre_ping=True is NOT used here: combined with the asyncpg async
    # driver it triggers a documented SQLAlchemy greenlet-context bug
    # ("MissingGreenlet: greenlet_spawn has not been called") on the first
    # checkout of a fresh connection — hit while building this. Connection
    # health is handled by asyncpg's own pool instead.
    return create_async_engine(_asyncpg_url(settings.database_url))


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: `session: AsyncSession = Depends(get_session)`."""
    async with get_sessionmaker()() as session:
        yield session
