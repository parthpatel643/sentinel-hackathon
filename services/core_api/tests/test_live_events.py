"""Live push: the event broker, the SSE stream, and zone events as alerts."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.app import app
from core_api.auth.dependencies import current_user, current_user_or_service
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.db.models import AuditLogEntry
from core_api.events.broker import EventBroker, LiveEvent, broker
from core_api.routers import events as events_router
from sentinel_core.config import get_settings

ADMIN = TokenPayload(user_id="u-1", email="admin@test.local", role="admin")


def _svc() -> dict[str, str]:
    return {"X-Service-Token": get_settings().edge_service_token.get_secret_value()}


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


async def test_a_slow_subscriber_loses_its_oldest_events_not_memory() -> None:
    local = EventBroker()
    async with local.subscribe() as queue:
        for i in range(300):
            local.publish(LiveEvent(kind="alert", payload={"n": i}, department_id=None))
        assert queue.qsize() == 256
        assert (await queue.get()).payload == {"n": 44}
    assert local.subscriber_count == 0


async def _read_stream(client: httpx.AsyncClient, publish: LiveEvent | None = None) -> list[str]:
    """Open the stream, publish once it is subscribed, return its events."""
    request = asyncio.create_task(client.get("/api/v1/events/stream"))
    for _ in range(200):
        if broker.subscriber_count:
            break
        await asyncio.sleep(0.01)
    if publish is not None:
        broker.publish(publish)
    response = await request
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return [chunk for chunk in response.text.split("\n\n") if chunk.startswith("event:")]


async def test_stream_delivers_events_and_respects_departments(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(events_router, "MAX_CONNECTION_S", 0.5)
    event = LiveEvent(kind="alert", payload={"id": "a-1"}, department_id="dept-a")

    delivered = await _read_stream(client, event)
    assert len(delivered) == 1
    kind, data = delivered[0].split("\n")
    assert kind == "event: alert"
    assert json.loads(data.removeprefix("data: ")) == {"id": "a-1"}

    scoped = TokenPayload(user_id="u-2", email="b@test.local", role="operator", department_id="b")
    app.dependency_overrides[current_user] = lambda: scoped
    assert await _read_stream(client, event) == []


async def _make_zone_event(client: httpx.AsyncClient) -> str:
    await client.post(
        "/api/v1/cameras",
        json={"camera_id": "zone-cam", "name": "Depot gate", "location": {"lat": 23, "lon": 72}},
    )
    zone = await client.post(
        "/api/v1/cameras/zone-cam/zones",
        json={
            "name": "Fuel store",
            "rule_type": "intrusion",
            "polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
        },
    )
    assert zone.status_code == 201, zone.text
    recorded = await client.post(
        "/api/v1/zone-events",
        headers=_svc(),
        json={
            "zone_id": zone.json()["id"],
            "camera_id": "zone-cam",
            "rule_type": "intrusion",
            "track_id": "7",
            "observed_at": datetime.now(UTC).isoformat(),
        },
    )
    assert recorded.status_code == 201, recorded.text
    listed = await client.get("/api/v1/zone-events", params={"status": "new"})
    return str(listed.json()[0]["id"])


async def test_zone_events_are_triaged_like_alerts_and_audited(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    event_id = await _make_zone_event(client)

    triaged = await client.patch(
        f"/api/v1/zone-events/{event_id}",
        json={"status": "acknowledged", "note": "patrol sent"},
    )

    assert triaged.status_code == 200, triaged.text
    assert triaged.json()["status"] == "acknowledged"
    assert triaged.json()["resolved_by"] == ADMIN.email
    assert triaged.json()["zone_name"] == "Fuel store"
    assert (await client.get("/api/v1/zone-events", params={"status": "new"})).json() == []
    actions = (await db_session.execute(select(AuditLogEntry.action))).scalars().all()
    assert "zone_event_status_changed" in actions


async def test_a_new_zone_event_is_pushed_to_consoles(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(events_router, "MAX_CONNECTION_S", 2.0)
    request = asyncio.create_task(client.get("/api/v1/events/stream"))
    for _ in range(200):
        if broker.subscriber_count:
            break
        await asyncio.sleep(0.01)

    await _make_zone_event(client)
    response = await request

    kinds = [line for line in response.text.splitlines() if line.startswith("event:")]
    assert "event: zone_event" in kinds
