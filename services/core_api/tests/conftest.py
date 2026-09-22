"""Registry integration tests need a REAL PostGIS-backed Postgres — SQLite
has no PostGIS support, so these cannot be mocked the way M0-M2's tests are.

Each test runs inside an outer transaction that is rolled back at teardown
(SQLAlchemy's documented `join_transaction_mode="create_savepoint"` recipe),
so application-level `session.commit()` calls only release a SAVEPOINT —
nothing a test does is ever actually persisted once it ends, and tests never
pollute each other or need their own cleanup logic.

The engine is created FRESH per test, not reused from
`core_api.db.base.get_engine()`'s process-wide cache: pytest-asyncio gives
each test function its own event loop by default, and an asyncpg connection
pool bound to one event loop breaks silently (every operation on it raises,
which `_database_reachable()`'s broad except then swallows into a skip) once
a later test runs on a different loop. This bit every test after the first
before it was fixed.

If the database is unreachable (e.g. CI running only the M0-M2 unit-test
tier without `make up`), these tests are SKIPPED, not failed — a green CI
run should not require the full docker-compose stack for every commit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sentinel_core.config import get_settings


def _test_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = _test_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("Postgres is not reachable — run `make up` for registry integration tests")

    try:
        async with engine.connect() as connection:
            outer_transaction = await connection.begin()
            session_factory = async_sessionmaker(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            async with session_factory() as session:
                yield session
            await outer_transaction.rollback()
    finally:
        await engine.dispose()
