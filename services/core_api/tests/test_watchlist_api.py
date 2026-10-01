"""The evaluation-day actions — arming a BOLO for the designated plate,
triaging the alert it raises, exporting the movement report — must each
leave a row in the hash-chained audit log, through the real HTTP routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.app import app
from core_api.auth.dependencies import current_user
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.db.models import AuditLogEntry, Detection
from core_api.detections.schemas import DetectionIn
from core_api.detections.service import ingest_detection
from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import upsert_camera

OPERATOR = TokenPayload(user_id="u-9", email="duty.officer@test.local", role="operator")


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[current_user] = lambda: OPERATOR
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _seed_sighting(session: AsyncSession) -> None:
    await upsert_camera(
        session,
        camera_id="audit-cam-01",
        name="Audit junction",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=23.02, lon=72.57),
        tier="a_continuous",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )
    await ingest_detection(
        session,
        DetectionIn(
            event_id="01JAUDIT00000000000000001",
            camera_id="audit-cam-01",
            plate_text="GJ18AB4321",
            plate_normalised="GJ18AB4321",
            plate_ambiguity_key="GJ18AB4321",
            plate_confidence=0.93,
            pts_ms=1.0,
            observed_at=datetime.now(UTC),
            node_id="edge-test",
        ),
    )


async def _audit(session: AsyncSession) -> list[AuditLogEntry]:
    rows = await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.seq))
    return list(rows.scalars())


async def test_bolo_triage_and_export_are_all_audited(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_sighting(db_session)

    bolo = await client.post(
        "/api/v1/bolo",
        json={"plate": "GJ 18 AB 4321", "entry_type": "stolen_vehicle", "priority": "high"},
    )
    assert bolo.status_code == 201, bolo.text
    assert bolo.json()["retro_alerts_created"] == 1
    assert bolo.json()["watchlist_entry"]["requested_by"] == OPERATOR.email

    alert = (await client.get("/api/v1/alerts")).json()[0]
    triage = await client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={"status": "acknowledged", "resolution_note": "unit dispatched"},
    )
    assert triage.status_code == 200, triage.text

    report = await client.get("/api/v1/vehicles/GJ18AB4321/movement-report")
    assert report.status_code == 200

    entries = {e.action: e for e in await _audit(db_session)}
    assert entries["bolo_armed"].actor_email == OPERATOR.email
    assert entries["bolo_armed"].detail["retro_alerts_created"] == 1
    assert entries["alert_status_changed"].detail["status"] == "acknowledged"
    assert entries["movement_report_exported"].resource_id == "GJ18AB4321"


async def test_route_window_reaches_back_across_a_two_day_event(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_sighting(db_session)
    await db_session.execute(
        update(Detection)
        .where(Detection.event_id == "01JAUDIT00000000000000001")
        .values(created_at=datetime.now(UTC) - timedelta(hours=30))
    )

    default = await client.get("/api/v1/vehicles/GJ18AB4321/route")
    wider = await client.get("/api/v1/vehicles/GJ18AB4321/route", params={"window_hours": 48})
    too_wide = await client.get("/api/v1/vehicles/GJ18AB4321/route", params={"window_hours": 999})

    assert default.json()["total_sightings"] == 0
    assert wider.json()["total_sightings"] == 1
    assert too_wide.status_code == 422
