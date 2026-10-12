"""An edge worker replays detections it could not deliver; the API must
accept a replay of one it already stored without storing it twice."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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
from sentinel_core.schemas import DUPLICATE_OF_HEADER

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


SCENE = datetime(2026, 6, 17, 12, 31, 21, tzinfo=UTC)


def _read(
    event_id: str, *, camera_time: datetime | None, plate: str = "GJ11S7924"
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "camera_id": "dup-cam",
        "plate_text": plate,
        "plate_normalised": plate,
        "plate_ambiguity_key": plate,
        "plate_confidence": 0.95,
        "pts_ms": 1000.0,
        "observed_at": datetime(2026, 10, 12, 11, 0, tzinfo=UTC).isoformat(),
        "camera_time": camera_time.isoformat() if camera_time else None,
        "node_id": "edge-1",
    }


async def _post_reads(client: httpx.AsyncClient, *reads: dict[str, object]) -> list[httpx.Response]:
    created = await client.post(
        "/api/v1/cameras", json={"camera_id": "dup-cam", "name": "Duplicate junction"}
    )
    assert created.status_code == 201, created.text
    headers = {"X-Service-Token": get_settings().edge_service_token.get_secret_value()}
    return [await client.post("/api/v1/detections", json=r, headers=headers) for r in reads]


async def _stored(db_session: AsyncSession) -> int:
    count = await db_session.scalar(
        select(func.count()).select_from(Detection).where(Detection.camera_id == "dup-cam")
    )
    return int(count or 0)


async def test_the_same_sighting_under_a_new_event_id_is_stored_once(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """A recorded feed looping, a reconnect replaying its buffer, a restarted
    worker: the same plate at the same printed second on the same camera,
    arriving as a new event. It is the sighting already on file."""
    first, again = await _post_reads(
        client,
        _read("01JDUP0000000000000000001", camera_time=SCENE),
        _read("01JDUP0000000000000000002", camera_time=SCENE),
    )

    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json() == []
    assert again.headers[DUPLICATE_OF_HEADER] == "01JDUP0000000000000000001"
    assert await _stored(db_session) == 1


async def test_a_different_second_or_plate_is_a_different_sighting(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    responses = await _post_reads(
        client,
        _read("01JDUP0000000000000000001", camera_time=SCENE),
        _read("01JDUP0000000000000000002", camera_time=SCENE + timedelta(seconds=1)),
        _read("01JDUP0000000000000000003", camera_time=SCENE, plate="GJ03MH7800"),
    )

    assert [r.status_code for r in responses] == [201, 201, 201]
    assert not any(DUPLICATE_OF_HEADER in r.headers for r in responses)
    assert await _stored(db_session) == 3


async def test_reads_without_a_camera_time_are_never_taken_for_duplicates(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """No printed time, no evidence two reads are one moment: both kept."""
    responses = await _post_reads(
        client,
        _read("01JDUP0000000000000000001", camera_time=None),
        _read("01JDUP0000000000000000002", camera_time=None),
    )

    assert [r.status_code for r in responses] == [201, 201]
    assert await _stored(db_session) == 2


async def test_a_read_that_is_not_an_indian_registration_is_refused(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """A sign or a damaged frame, from any producer: not stored, not matched."""
    [refused] = await _post_reads(
        client, _read("01JDUP0000000000000000001", camera_time=SCENE, plate="CIRCLE")
    )

    assert refused.status_code == 422
    assert await _stored(db_session) == 0
