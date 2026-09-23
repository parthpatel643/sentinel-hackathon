"""Tests for M12's snapshot-serving / reveal-on-authorisation service —
path resolution against a real Postgres-backed Detection row (see
conftest.py's transaction-rollback isolation) plus the audit-event
recorder's pure logic."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.detections.schemas import DetectionIn
from core_api.detections.service import ingest_detection
from core_api.evidence.reveal import (
    record_reveal_audit,
    resolve_original_path,
    resolve_snapshot_path,
)
from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import upsert_camera
from sentinel_core.config import Settings

NOW = datetime.now(UTC).replace(microsecond=0)


async def _make_camera(session: AsyncSession, camera_id: str = "reveal-test-cam") -> None:
    await upsert_camera(
        session,
        camera_id=camera_id,
        name="Reveal Test Camera",
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


async def _make_detection(
    session: AsyncSession, *, event_id: str, snapshot_uri: str | None
) -> None:
    await ingest_detection(
        session,
        DetectionIn.model_validate(
            {
                "event_id": event_id,
                "camera_id": "reveal-test-cam",
                "plate_text": "GJ01AB1234",
                "plate_normalised": "GJ01AB1234",
                "plate_ambiguity_key": "GJ01AB1234",
                "plate_confidence": 0.9,
                "pts_ms": 1000.0,
                "observed_at": NOW,
                "node_id": "edge-local-01",
                "snapshot_uri": snapshot_uri,
            }
        ),
    )


def _settings(snapshots_dir: Path, originals_dir: Path) -> Settings:
    return Settings(
        snapshots_dir=str(snapshots_dir),
        snapshot_originals_dir=str(originals_dir),
    )


async def test_resolve_snapshot_path_returns_none_when_detection_has_no_snapshot(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    await _make_detection(db_session, event_id="evt-no-snap", snapshot_uri=None)

    with tempfile.TemporaryDirectory() as blurred, tempfile.TemporaryDirectory() as originals:
        path = await resolve_snapshot_path(
            db_session, "evt-no-snap", _settings(Path(blurred), Path(originals))
        )

    assert path is None


async def test_resolve_snapshot_path_returns_none_for_an_unknown_event_id(
    db_session: AsyncSession,
) -> None:
    with tempfile.TemporaryDirectory() as blurred, tempfile.TemporaryDirectory() as originals:
        path = await resolve_snapshot_path(
            db_session, "evt-does-not-exist", _settings(Path(blurred), Path(originals))
        )

    assert path is None


async def test_resolve_snapshot_path_returns_the_file_when_it_exists_on_disk(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    await _make_detection(
        db_session, event_id="evt-with-snap", snapshot_uri="snapshot://evt-with-snap"
    )

    with tempfile.TemporaryDirectory() as blurred, tempfile.TemporaryDirectory() as originals:
        blurred_path = Path(blurred) / "evt-with-snap.jpg"
        blurred_path.write_bytes(b"fake-jpeg-bytes")

        path = await resolve_snapshot_path(
            db_session, "evt-with-snap", _settings(Path(blurred), Path(originals))
        )

        assert path == blurred_path


async def test_resolve_snapshot_path_returns_none_if_the_db_says_yes_but_the_file_is_missing(
    db_session: AsyncSession,
) -> None:
    """The detection row claims a snapshot exists, but nothing was ever
    actually written to disk (or it was cleaned up) — must 404, not crash."""
    await _make_camera(db_session)
    await _make_detection(
        db_session, event_id="evt-missing-file", snapshot_uri="snapshot://evt-missing-file"
    )

    with tempfile.TemporaryDirectory() as blurred, tempfile.TemporaryDirectory() as originals:
        path = await resolve_snapshot_path(
            db_session, "evt-missing-file", _settings(Path(blurred), Path(originals))
        )

    assert path is None


async def test_resolve_original_path_resolves_against_the_originals_directory(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    await _make_detection(
        db_session, event_id="evt-original", snapshot_uri="snapshot://evt-original"
    )

    with tempfile.TemporaryDirectory() as blurred, tempfile.TemporaryDirectory() as originals:
        original_path = Path(originals) / "evt-original.jpg"
        original_path.write_bytes(b"fake-unblurred-jpeg-bytes")

        path = await resolve_original_path(
            db_session, "evt-original", _settings(Path(blurred), Path(originals))
        )

        assert path == original_path


def test_record_reveal_audit_returns_the_captured_reason_and_actor() -> None:
    event = record_reveal_audit(
        event_id="evt-audit-001",
        actor_email="admin@sentinel-platform.com",
        reason="Case FIR/2024/1",
    )

    assert event.event_id == "evt-audit-001"
    assert event.actor_email == "admin@sentinel-platform.com"
    assert event.reason == "Case FIR/2024/1"
    assert event.revealed_at.tzinfo is not None
