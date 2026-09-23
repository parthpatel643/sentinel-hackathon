"""Async SQLAlchemy engine and session factory.

One engine per process, created lazily so importing this module never
requires a live database (important for unit tests that only need the ORM
models' shape, not a connection).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from functools import lru_cache
from typing import ClassVar

from fastapi import Request
from sqlalchemy import DateTime, text
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
    """Every ORM model in core_api inherits from this.

    `datetime` is mapped to a timezone-aware column (Postgres `timestamptz`)
    for every model, project-wide, in this one place — not per-column. Every
    datetime in the domain model (`sentinel_core.schemas.events.Event` et al)
    is UTC-aware (`datetime.now(UTC)`); a naive `TIMESTAMP` column raises
    asyncpg's "can't subtract offset-naive and offset-aware datetimes" the
    first time an aware value is written or compared against it — hit while
    building the M4 detections/watchlist tables, fixed here rather than by
    stripping tzinfo at every call site.
    """

    type_annotation_map: ClassVar[dict[type, DateTime]] = {datetime: DateTime(timezone=True)}


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
    # app_database_url, not database_url: core_api's own request-handling
    # queries run as the narrower `sentinel_app` role (not the superuser
    # migration role), which is what actually makes the department-tenancy
    # RLS policies (see the 23c60ee4c006 migration) bind — Postgres RLS is
    # unconditionally bypassed for superusers/table owners, so this engine
    # being on the restricted role is not optional if RLS is meant to do
    # anything at all. See docs/08-SECURITY-HARDENING.md.
    #
    # pool_pre_ping=True is NOT used here: combined with the asyncpg async
    # driver it triggers a documented SQLAlchemy greenlet-context bug
    # ("MissingGreenlet: greenlet_spawn has not been called") on the first
    # checkout of a fresh connection — hit while building this. Connection
    # health is handled by asyncpg's own pool instead.
    return create_async_engine(_asyncpg_url(settings.app_database_url))


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: `session: AsyncSession = Depends(get_session)`.

    Applies the department-tenancy scope (docs/08-SECURITY-HARDENING.md)
    for the request's *first* transaction by setting the
    `app.current_department_id` GUC the RLS policies read — `request.state
    .department_id` is populated by `TenancyMiddleware`
    (core_api/security/tenancy.py) from the caller's JWT, best-effort and
    before any route dependency runs.

    `SET LOCAL` does not accept bind parameters (Postgres rejects `SET
    LOCAL x = $1` outright — it's a configuration command, not a DML
    query), so the value is validated as a real UUID (or treated as
    "unset") and embedded as a literal instead of parameterized — safe
    specifically because a validated UUID's string form can never contain
    a quote character or anything else SQL-meaningful.

    Known sharp edge: `SET LOCAL` only lasts for one transaction. A route
    that calls `session.commit()` mid-handler and then issues further
    queries in the same request loses the restriction for those later
    queries (no current route does this on a department-scoped read path,
    but it's a real limitation, not a hidden one).
    """
    async with get_sessionmaker()() as session:
        department_id = getattr(request.state, "department_id", None)
        safe_value = ""
        if department_id:
            try:
                safe_value = str(uuid.UUID(str(department_id)))
            except ValueError:
                safe_value = ""
        await session.execute(text(f"SET LOCAL app.current_department_id = '{safe_value}'"))
        yield session

