"""An edge worker replays detections it could not deliver; the API must
accept a replay of one it already stored without storing it twice."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.app import app
from core_api.auth.dependencies import current_user, current_user_or_service
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.db.models import Detection
from sentinel_core.config import get_settings

ADMIN = TokenPayload(user_id="u-1", email="admin@test.local", role="admin")


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[current_user] = lambda: ADMIN
    app.dependency_overrides[current_user_or_service] = lambda: ADMIN
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_a_replayed_detection_is_accepted_once(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    created = await client.post(
        "/api/v1/cameras", json={"camera_id": "replay-cam", "name": "Replay junction"}
    )
    assert created.status_code == 201, created.text
    body = {
        "event_id": "01JREPLAY000000000000000001",
        "camera_id": "replay-cam",
        "plate_text": "GJ01AB1234",
        "plate_normalised": "GJ01AB1234",
        "plate_ambiguity_key": "6J0148124",
        "plate_confidence": 0.93,
        "pts_ms": 1200.0,
        "observed_at": datetime(2026, 10, 12, 9, 30, tzinfo=UTC).isoformat(),
        "node_id": "edge-1",
    }
    headers = {"X-Service-Token": get_settings().edge_service_token.get_secret_value()}

    first = await client.post("/api/v1/detections", json=body, headers=headers)
    replay = await client.post("/api/v1/detections", json=body, headers=headers)

    assert (first.status_code, replay.status_code) == (201, 201)
    assert replay.json() == []
    stored = await db_session.scalar(
        select(func.count()).select_from(Detection).where(Detection.event_id == body["event_id"])
    )
    assert stored == 1
