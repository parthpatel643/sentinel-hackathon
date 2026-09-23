"""Field PWA backend tests against a real Postgres. See conftest.py for the
transaction-rollback isolation — nothing here is ever actually persisted
once a test ends."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.detections.schemas import DetectionIn
from core_api.detections.service import ingest_detection
from core_api.field.service import list_sightings, lookup_plate, record_sighting, sighting_to_out
from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import upsert_camera
from core_api.watchlist.schemas import WatchlistEntryCreate
from core_api.watchlist.service import create_watchlist_entry

NOW = datetime.now(UTC).replace(microsecond=0)


async def _make_camera(session: AsyncSession, camera_id: str = "field-cam-01") -> None:
    await upsert_camera(
        session,
        camera_id=camera_id,
        name="Field Test Camera",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=23.0225, lon=72.5714),
        tier="a_continuous",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )


async def test_lookup_plate_is_clear_when_nothing_matches(db_session: AsyncSession) -> None:
    result = await lookup_plate(db_session, "GJ01AB1234")

    assert result.status == "clear"
    assert result.matches == []
    assert result.last_seen_at is None


async def test_lookup_plate_reports_the_highest_priority_active_match(
    db_session: AsyncSession,
) -> None:
    await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="suspect", priority="low")
    )
    await create_watchlist_entry(
        db_session,
        WatchlistEntryCreate(plate="GJ01AB1234", entry_type="stolen_vehicle", priority="critical"),
    )

    result = await lookup_plate(db_session, "GJ01AB1234")

    assert result.status == "stolen_vehicle"
    assert len(result.matches) == 2


async def test_lookup_plate_includes_the_last_sighting(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    await ingest_detection(
        db_session,
        DetectionIn.model_validate(
            {
                "event_id": "evt-field-lookup-1",
                "camera_id": "field-cam-01",
                "plate_text": "GJ01AB1234",
                "plate_normalised": "GJ01AB1234",
                "plate_ambiguity_key": "GJ01AB1234",
                "plate_confidence": 0.9,
                "pts_ms": 1000.0,
                "observed_at": NOW,
                "node_id": "edge-local-01",
            }
        ),
    )

    result = await lookup_plate(db_session, "GJ01AB1234")

    assert result.last_seen_at == NOW
    assert result.last_seen_camera_name == "Field Test Camera"


async def test_record_sighting_is_idempotent_on_client_report_id(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    report_1, created_1 = await record_sighting(
        db_session,
        reports_dir=tmp_path,
        client_report_id="device-abc-report-1",
        reported_by="officer@example.com",
        plate_text="GJ01AB1234",
        lat=23.0225,
        lon=72.5714,
        notes="Seen near the market",
        photo_bytes=None,
    )
    assert created_1 is True

    report_2, created_2 = await record_sighting(
        db_session,
        reports_dir=tmp_path,
        client_report_id="device-abc-report-1",
        reported_by="officer@example.com",
        plate_text="GJ01AB1234",
        lat=23.0225,
        lon=72.5714,
        notes="Seen near the market",
        photo_bytes=None,
    )
    assert created_2 is False
    assert report_2.id == report_1.id

    reports = await list_sightings(db_session)
    assert len([r for r in reports if r.client_report_id == "device-abc-report-1"]) == 1


async def test_record_sighting_saves_the_photo_and_hashes_its_name(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    report, created = await record_sighting(
        db_session,
        reports_dir=tmp_path,
        client_report_id="device-abc-report-2",
        reported_by="officer@example.com",
        plate_text="GJ01AB1234",
        lat=None,
        lon=None,
        notes=None,
        photo_bytes=b"fake-jpeg-bytes",
    )

    assert created is True
    assert report.photo_path is not None
    photo_path = Path(report.photo_path)
    assert await asyncio.to_thread(photo_path.is_file)
    assert await asyncio.to_thread(photo_path.read_bytes) == b"fake-jpeg-bytes"

    out = sighting_to_out(report)
    assert out.has_photo is True
