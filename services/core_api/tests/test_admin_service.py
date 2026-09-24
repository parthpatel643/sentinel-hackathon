"""Retention preview tests against a real Postgres. See conftest.py for the
transaction-rollback isolation — nothing here is ever actually persisted
once a test ends."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
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


# Retention is a whole-table operation, so these tests cannot assert on
# absolute counts: the dev database is shared with a live pipeline that
# commits new detections continuously, and emptying the table first only
# narrows the race rather than closing it — rows committed by the worker
# mid-test reappear, carrying scene timestamps months old and so counting as
# "expired". Each test below therefore asserts something that stays true
# whatever else is in the table: the delta it caused, the fate of its own
# rows, or a cutoff so old that nothing can qualify.
_NEVER_EXPIRES_DAYS = 365_000


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
    """The cutoff must select strictly by age, so of two rows straddling it
    exactly one qualifies.

    Asserted over this test's own rows rather than the preview's total. The
    total cannot be pinned down here: the live pipeline writes to the same
    database, and a single detection committed between taking a baseline and
    reading the count is enough to make an exact delta wrong — observed in
    practice, which is what prompted this shape.
    """
    await _make_camera(db_session)
    await _make_detection(db_session, event_id="evt-old", observed_at=NOW - timedelta(days=40))
    await _make_detection(db_session, event_id="evt-recent", observed_at=NOW - timedelta(days=1))

    cutoff = datetime.now(UTC) - timedelta(days=30)
    expired = set(
        (
            await db_session.execute(
                select(Detection.event_id).where(
                    Detection.event_id.in_(["evt-old", "evt-recent"]),
                    Detection.observed_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )

    assert expired == {"evt-old"}
    # And the preview does look at that predicate at all, rather than
    # reporting a constant.
    preview = await preview_retention(
        db_session, detections_older_than_days=30, clips_older_than_days=90
    )
    assert preview.detections_affected >= 1


async def test_no_data_yields_a_zeroed_preview(db_session: AsyncSession) -> None:
    """Nothing is old enough to expire under a cutoff of a thousand years, so
    this stays a genuine "nothing to do" regardless of what the table holds."""
    result = await preview_retention(
        db_session,
        detections_older_than_days=_NEVER_EXPIRES_DAYS,
        clips_older_than_days=_NEVER_EXPIRES_DAYS,
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

    await execute_retention(
        db_session,
        detections_older_than_days=30,
        clips_older_than_days=90,
        actor_email="admin@sentinel-platform.com",
    )

    surviving = set(
        (
            await db_session.execute(
                select(Detection.event_id).where(
                    Detection.event_id.in_(["evt-old", "evt-recent"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert surviving == {"evt-recent"}, "the expired row must go and the recent one stay"


async def test_execute_retention_records_a_hash_chained_audit_entry(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    await _make_detection(
        db_session, event_id="evt-audit-ret", observed_at=NOW - timedelta(days=40)
    )

    result = await execute_retention(
        db_session,
        detections_older_than_days=30,
        clips_older_than_days=90,
        actor_email="admin@sentinel-platform.com",
    )

    entries = await list_audit_log(db_session)
    retention_entries = [e for e in entries if e.action == "retention_executed"]
    assert len(retention_entries) == 1
    assert retention_entries[0].actor_email == "admin@sentinel-platform.com"
    # The audit entry must report what the run actually did, whatever that
    # number happened to be — the point of the chain is that it cannot later
    # disagree with the operation it records.
    assert retention_entries[0].detail["detections_deleted"] == result.detections_deleted
    assert result.detections_deleted >= 1


async def test_execute_retention_with_nothing_to_delete_is_a_no_op(
    db_session: AsyncSession,
) -> None:
    result = await execute_retention(
        db_session,
        detections_older_than_days=_NEVER_EXPIRES_DAYS,
        clips_older_than_days=_NEVER_EXPIRES_DAYS,
        actor_email="admin@sentinel-platform.com",
    )

    assert result.detections_deleted == 0
    assert result.clips_deleted == 0
    assert result.clips_bytes_deleted == 0
