"""Retention preview tests against a real Postgres. See conftest.py for the
transaction-rollback isolation — nothing here is ever actually persisted
once a test ends."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.admin.service import (
    check_integration_statuses,
    execute_retention,
    list_audit_log,
    preview_retention,
)
from core_api.db.models import Detection
from core_api.detections.schemas import DetectionIn
from core_api.detections.service import ingest_detection
from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import upsert_camera

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest_asyncio.fixture(autouse=True)
async def _empty_detections(db_session: AsyncSession) -> AsyncIterator[None]:
    """Retention is a whole-table operation: the preview counts every
    detection older than the cutoff, and execute deletes them. These tests
    therefore assert on absolute counts, which only holds if they own the
    table.

    Against a dev database that has been running the live pipeline, it holds
    not at all — a few hundred real detections make "nothing to delete" delete
    plenty. Rolled back by `db_session`, so a real capture survives.
    """
    await db_session.execute(delete(Detection))
    yield


async def _make_camera(session: AsyncSession, camera_id: str = "retention-cam-01") -> None:
    await upsert_camera(
        session,
        camera_id=camera_id,
        name="Retention Test Camera",
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


async def _make_detection(session: AsyncSession, *, event_id: str, observed_at: datetime) -> None:
    await ingest_detection(
        session,
        DetectionIn.model_validate(
            {
                "event_id": event_id,
                "camera_id": "retention-cam-01",
                "plate_text": "GJ01AB1234",
                "plate_normalised": "GJ01AB1234",
                "plate_ambiguity_key": "GJ01AB1234",
                "plate_confidence": 0.9,
                "pts_ms": 1000.0,
                "observed_at": observed_at,
                "node_id": "edge-local-01",
            }
        ),
    )


async def test_only_detections_older_than_the_cutoff_are_counted(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    await _make_detection(db_session, event_id="evt-old", observed_at=NOW - timedelta(days=40))
    await _make_detection(db_session, event_id="evt-recent", observed_at=NOW - timedelta(days=1))

    result = await preview_retention(
        db_session, detections_older_than_days=30, clips_older_than_days=90
    )

    assert result.detections_affected == 1


async def test_no_data_yields_a_zeroed_preview(db_session: AsyncSession) -> None:
    result = await preview_retention(
        db_session, detections_older_than_days=30, clips_older_than_days=90
    )

    assert result.detections_affected == 0
    assert result.clips_affected == 0
    assert result.clips_bytes_affected == 0


async def test_check_integration_statuses_reports_all_four_providers_connected() -> None:
    statuses = await check_integration_statuses()

    provider_ids = {s.provider_id for s in statuses}
    assert provider_ids == {"vahan", "sarthi", "egujcop", "afis"}
    assert all(s.mode == "mock" for s in statuses)
    assert all(s.connected for s in statuses)
    assert all(s.sample_latency_ms is not None and s.sample_latency_ms >= 0 for s in statuses)
    # Honesty check: the detail text must not overclaim a live connection.
    assert all("mock" in s.detail.lower() for s in statuses)


async def test_execute_retention_deletes_only_detections_older_than_the_cutoff(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    await _make_detection(db_session, event_id="evt-old", observed_at=NOW - timedelta(days=40))
    await _make_detection(db_session, event_id="evt-recent", observed_at=NOW - timedelta(days=1))

    result = await execute_retention(
        db_session,
        detections_older_than_days=30,
        clips_older_than_days=90,
        actor_email="admin@sentinel-platform.com",
    )

    assert result.detections_deleted == 1
    remaining = await preview_retention(
        db_session, detections_older_than_days=0, clips_older_than_days=90
    )
    assert remaining.detections_affected == 1  # only "evt-recent" is left


async def test_execute_retention_records_a_hash_chained_audit_entry(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    await _make_detection(
        db_session, event_id="evt-audit-ret", observed_at=NOW - timedelta(days=40)
    )

    await execute_retention(
        db_session,
        detections_older_than_days=30,
        clips_older_than_days=90,
        actor_email="admin@sentinel-platform.com",
    )

    entries = await list_audit_log(db_session)
    retention_entries = [e for e in entries if e.action == "retention_executed"]
    assert len(retention_entries) == 1
    assert retention_entries[0].actor_email == "admin@sentinel-platform.com"
    assert retention_entries[0].detail["detections_deleted"] == 1


async def test_execute_retention_with_nothing_to_delete_is_a_no_op(
    db_session: AsyncSession,
) -> None:
    result = await execute_retention(
        db_session,
        detections_older_than_days=30,
        clips_older_than_days=90,
        actor_email="admin@sentinel-platform.com",
    )

    assert result.detections_deleted == 0
    assert result.clips_deleted == 0
    assert result.clips_bytes_deleted == 0
