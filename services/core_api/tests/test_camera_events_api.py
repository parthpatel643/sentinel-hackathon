"""Camera view alerts through the real HTTP routes: a moved camera raises one
alert, a restored view closes it, triage is audited, and the before/after
frames are served only for an alert the caller can see."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.app import app
from core_api.auth.dependencies import current_user, current_user_or_signed_url
from core_api.auth.service import TokenPayload
from core_api.camera_events.service import RESTORED_BY
from core_api.db.base import get_session
from core_api.db.models import AuditLogEntry
from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import upsert_camera
from sentinel_core.config import get_settings

OPERATOR = TokenPayload(user_id="u-7", email="control.room@test.local", role="operator")
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
PROCESSED_AT = datetime(2026, 10, 12, 5, 0, tzinfo=UTC)
SCENE_TIME = datetime(2026, 8, 8, 15, 40, 33, tzinfo=UTC)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[current_user] = lambda: OPERATOR
    app.dependency_overrides[current_user_or_signed_url] = lambda: OPERATOR
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "snapshots_dir", str(tmp_path))
    return tmp_path


def _service() -> dict[str, str]:
    return {"X-Service-Token": get_settings().edge_service_token.get_secret_value()}


async def _camera(session: AsyncSession, camera_id: str = "view-cam-01") -> None:
    await upsert_camera(
        session,
        camera_id=camera_id,
        name="Ring road junction",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=23.02, lon=72.57),
        tier="b_sampled",
        status="live",
        source="manual",
        attributes={},
        profiles=[],
    )


def _moved(event_id: str = "01JVIEW000000000000000001", **extra: object) -> dict[str, object]:
    return {
        "event_id": event_id,
        "camera_id": "view-cam-01",
        "kind": "view_shifted",
        "shift_pct": 12.3,
        "rotation_deg": 0.1,
        "scale": 1.0,
        "match_ratio": 0.27,
        "observed_at": PROCESSED_AT.isoformat(),
        "camera_time": SCENE_TIME.isoformat(),
        "has_snapshots": True,
    } | extra


async def test_a_moved_camera_raises_one_alert_however_often_it_is_reported(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _camera(db_session)

    first = await client.post("/api/v1/camera-events", json=_moved(), headers=_service())
    retried = await client.post("/api/v1/camera-events", json=_moved(), headers=_service())
    again = await client.post(
        "/api/v1/camera-events", json=_moved("01JVIEW000000000000000002"), headers=_service()
    )

    assert first.status_code == 201, first.text
    assert retried.status_code == again.status_code == 200
    assert retried.json()["id"] == again.json()["id"] == first.json()["id"]
    listed = (await client.get("/api/v1/camera-events", params={"status": "new"})).json()
    assert len(listed) == 1
    assert listed[0]["camera_time"] == SCENE_TIME.isoformat().replace("+00:00", "Z")
    assert listed[0]["shift_pct"] == 12.3


async def test_a_different_kind_of_change_is_its_own_alert(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _camera(db_session)
    await client.post("/api/v1/camera-events", json=_moved(), headers=_service())
    lost = await client.post(
        "/api/v1/camera-events",
        json=_moved("01JVIEW000000000000000003", kind="view_unrecognised", shift_pct=None),
        headers=_service(),
    )
    assert lost.status_code == 201
    assert len((await client.get("/api/v1/camera-events")).json()) == 2


async def test_a_restored_view_closes_its_open_alerts(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _camera(db_session)
    await client.post("/api/v1/camera-events", json=_moved(), headers=_service())

    restored = await client.post(
        "/api/v1/camera-events/restored",
        json={"camera_id": "view-cam-01", "observed_at": PROCESSED_AT.isoformat()},
        headers=_service(),
    )

    assert restored.status_code == 200
    [event] = restored.json()
    assert event["status"] == "resolved"
    assert event["resolved_by"] == RESTORED_BY
    assert event["restored_at"] is not None
    # Closed, so a later move is a fresh alert.
    later = await client.post(
        "/api/v1/camera-events", json=_moved("01JVIEW000000000000000004"), headers=_service()
    )
    assert later.status_code == 201


async def test_triage_is_audited(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await _camera(db_session)
    created = (await client.post("/api/v1/camera-events", json=_moved(), headers=_service())).json()

    patched = await client.patch(
        f"/api/v1/camera-events/{created['id']}",
        json={"status": "false_positive", "note": "PTZ tour"},
    )

    assert patched.status_code == 200
    assert patched.json()["status"] == "false_positive"
    assert patched.json()["resolved_by"] == OPERATOR.email
    rows = (await db_session.execute(select(AuditLogEntry))).scalars().all()
    audit = [r for r in rows if r.action == "camera_event_status_changed"]
    assert len(audit) == 1
    assert audit[0].detail["status"] == "false_positive"


async def test_ingest_needs_the_service_token(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _camera(db_session)
    response = await client.post(
        "/api/v1/camera-events", json=_moved(), headers={"X-Service-Token": "nope"}
    )
    assert response.status_code in (401, 403)


async def test_before_and_after_frames_are_uploaded_and_served(
    client: httpx.AsyncClient, db_session: AsyncSession, snapshots: Path
) -> None:
    await _camera(db_session)
    event_id = "01JVIEW000000000000000005"
    await client.post("/api/v1/camera-events", json=_moved(event_id), headers=_service())

    for which in ("before", "after"):
        upload = await client.put(
            f"/api/v1/camera-events/{event_id}/snapshot/{which}",
            files={"blurred": (f"{which}.jpg", JPEG, "image/jpeg")},
            headers=_service(),
        )
        assert upload.status_code == 204, upload.text

    after = await client.get(f"/api/v1/camera-events/{event_id}/snapshot/after")
    assert after.status_code == 200
    assert after.content == JPEG
    assert (snapshots / f"{event_id}-before.jpg").read_bytes() == JPEG


async def test_frames_are_not_served_for_an_unknown_event(
    client: httpx.AsyncClient, snapshots: Path
) -> None:
    """A frame on disk is served only through an event the caller can see —
    department scoping covers the evidence, not only the row."""
    (snapshots / "01JVIEWORPHAN0000000000001-after.jpg").write_bytes(JPEG)
    response = await client.get("/api/v1/camera-events/01JVIEWORPHAN0000000000001/snapshot/after")
    assert response.status_code == 404


async def test_uploads_are_held_to_jpegs_and_safe_names(
    client: httpx.AsyncClient, db_session: AsyncSession, snapshots: Path
) -> None:
    not_jpeg = await client.put(
        "/api/v1/camera-events/01JVIEW000000000000000006/snapshot/after",
        files={"blurred": ("x.jpg", b"GIF89a", "image/jpeg")},
        headers=_service(),
    )
    traversal = await client.put(
        "/api/v1/camera-events/..%2F..%2Fetc/snapshot/after",
        files={"blurred": ("x.jpg", JPEG, "image/jpeg")},
        headers=_service(),
    )
    assert not_jpeg.status_code == 415
    assert traversal.status_code in (404, 422)
    assert not any(snapshots.iterdir())  # noqa: ASYNC240 - a test assertion, not a request path
