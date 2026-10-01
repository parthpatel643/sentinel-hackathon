"""The development password printed in the README must not open an account
anywhere but a developer's own machine."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.app import app
from core_api.auth.service import hash_password
from core_api.db.base import get_session
from core_api.db.models import User
from core_api.routers import auth as auth_router
from sentinel_core.config import PUBLISHED_DEV_PASSWORD, Settings


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    db_session.add(
        User(
            email="demo@sentinel-platform.example",
            hashed_password=hash_password(PUBLISHED_DEV_PASSWORD),
            full_name="Demo",
            role="admin",
        )
    )
    await db_session.flush()
    app.dependency_overrides[get_session] = _session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _login(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"email": "demo@sentinel-platform.example", "password": PUBLISHED_DEV_PASSWORD},
    )


async def test_the_published_password_works_on_a_developer_machine(
    client: httpx.AsyncClient,
) -> None:
    assert (await _login(client)).status_code == 200


async def test_the_published_password_is_refused_anywhere_else(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_router, "get_settings", lambda: Settings(environment="prod"))

    response = await _login(client)

    assert response.status_code == 403
    assert "--reset-password" in response.json()["detail"]
