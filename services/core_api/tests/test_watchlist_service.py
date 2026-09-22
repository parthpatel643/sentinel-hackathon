"""Watchlist entry, correlation, dedup and BOLO tests against a real
Postgres. See conftest.py for the transaction-rollback isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.detections.schemas import DetectionIn
from core_api.detections.service import ingest_detection
from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import upsert_camera
from core_api.watchlist.schemas import AlertUpdate, WatchlistEntryCreate
from core_api.watchlist.service import (
    ALERT_DEDUP_WINDOW,
    correlate_detection,
    create_watchlist_entry,
    list_alerts,
    list_watchlist_entries,
    retro_scan,
    update_alert,
    update_watchlist_entry,
)

ANCHOR = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _make_camera(session: AsyncSession, camera_id: str = "wl-cam-01") -> None:
    await upsert_camera(
        session,
        camera_id=camera_id,
        name="Watchlist Test Camera",
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


def _detection_in(**overrides: object) -> DetectionIn:
    defaults: dict[str, object] = {
        "event_id": "01JEVT0000000000000000010",
        "camera_id": "wl-cam-01",
        "plate_text": "GJ01AB1234",
        "plate_normalised": "GJ01AB1234",
        "plate_ambiguity_key": "6J01481234",
        "plate_confidence": 0.9,
        "pts_ms": 1000.0,
        "observed_at": ANCHOR,
        "node_id": "edge-local-01",
    }
    defaults.update(overrides)
    return DetectionIn.model_validate(defaults)


async def test_create_watchlist_entry_normalises_and_keys_the_plate(
    db_session: AsyncSession,
) -> None:
    entry = await create_watchlist_entry(
        db_session,
        WatchlistEntryCreate(plate="gj 01 ab 1234", entry_type="stolen", priority="high"),
    )

    assert entry.plate_normalised == "GJ01AB1234"
    assert entry.plate_ambiguity_key == "6J01481234"
    assert entry.active is True


async def test_list_watchlist_entries_defaults_to_active_only(db_session: AsyncSession) -> None:
    active = await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="stolen")
    )
    inactive = await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ05CD9999", entry_type="stolen")
    )
    inactive.active = False
    await db_session.flush()

    entries = await list_watchlist_entries(db_session)
    assert {e.id for e in entries} == {active.id}

    all_entries = await list_watchlist_entries(db_session, active_only=False)
    assert {e.id for e in all_entries} == {active.id, inactive.id}


async def test_correlate_detection_creates_an_alert_for_a_matching_watchlist_entry(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    entry = await create_watchlist_entry(
        db_session,
        WatchlistEntryCreate(plate="GJ01AB1234", entry_type="stolen", priority="critical"),
    )
    detection = await ingest_detection(db_session, _detection_in())

    alerts = await correlate_detection(db_session, detection)

    assert len(alerts) == 1
    assert alerts[0].watchlist_entry_id == entry.id
    assert alerts[0].match_rung == "exact"
    assert alerts[0].sighting_count == 1
    assert alerts[0].priority_score == 1.0 * 0.9 * 1.0  # critical * confidence * exact-rung


async def test_correlate_detection_finds_nothing_for_an_unwatched_plate(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    detection = await ingest_detection(db_session, _detection_in())

    alerts = await correlate_detection(db_session, detection)

    assert alerts == []


async def test_repeated_sightings_within_the_dedup_window_collapse_into_one_alert(
    db_session: AsyncSession,
) -> None:
    """A car idling at the same junction for a few minutes must raise the
    sighting count on one alert, not spawn a new alert per frame."""
    await _make_camera(db_session)
    await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="stolen")
    )

    first = await ingest_detection(db_session, _detection_in(event_id="evt-1", observed_at=ANCHOR))
    await correlate_detection(db_session, first)

    second_time = ANCHOR + (ALERT_DEDUP_WINDOW / 2)
    second = await ingest_detection(
        db_session, _detection_in(event_id="evt-2", observed_at=second_time)
    )
    alerts = await correlate_detection(db_session, second)

    assert len(alerts) == 1
    assert alerts[0].sighting_count == 2
    assert alerts[0].last_seen_at == second_time

    all_alerts = await list_alerts(db_session)
    assert len(all_alerts) == 1


async def test_a_sighting_outside_the_dedup_window_creates_a_new_alert(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session)
    await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="stolen")
    )

    first = await ingest_detection(db_session, _detection_in(event_id="evt-1", observed_at=ANCHOR))
    await correlate_detection(db_session, first)

    later = ANCHOR + ALERT_DEDUP_WINDOW + timedelta(minutes=1)
    second = await ingest_detection(db_session, _detection_in(event_id="evt-2", observed_at=later))
    alerts = await correlate_detection(db_session, second)

    assert len(alerts) == 1
    assert alerts[0].sighting_count == 1  # a distinct alert, not a continuation

    all_alerts = await list_alerts(db_session)
    assert len(all_alerts) == 2


async def test_bolo_retro_scan_finds_a_detection_already_on_file(db_session: AsyncSession) -> None:
    """The flagship BOLO moment: a detection recorded before the watchlist
    entry existed must still surface as an alert once the entry is armed."""
    await _make_camera(db_session)
    detection = await ingest_detection(db_session, _detection_in())
    # No watchlist entry yet — the plate is not being watched when this is seen.
    assert await correlate_detection(db_session, detection) == []

    entry = await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="bolo", priority="high")
    )
    retro_alerts = await retro_scan(db_session, entry)

    assert len(retro_alerts) == 1
    assert retro_alerts[0].detection_event_id == detection.event_id
    assert retro_alerts[0].watchlist_entry_id == entry.id


async def test_retro_scan_matches_on_ambiguity_class_too(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    misread_text = "GJ014B1234"
    detection = await ingest_detection(
        db_session,
        _detection_in(
            plate_text=misread_text,
            plate_normalised=misread_text,
            plate_ambiguity_key="6J01481234",  # same class as GJ01AB1234
        ),
    )

    entry = await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="bolo")
    )
    retro_alerts = await retro_scan(db_session, entry)

    assert len(retro_alerts) == 1
    assert retro_alerts[0].match_rung == "ambiguity_class"
    assert retro_alerts[0].detection_event_id == detection.event_id


async def test_list_alerts_filters_by_status(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    entry = await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="stolen")
    )
    detection = await ingest_detection(db_session, _detection_in())
    await correlate_detection(db_session, detection)
    [alert] = await list_alerts(db_session)

    await update_alert(db_session, alert.id, AlertUpdate(status="acknowledged"))

    assert [a.status for a in await list_alerts(db_session, status="acknowledged")] == [
        "acknowledged"
    ]
    assert await list_alerts(db_session, status="new") == []
    assert entry.id == alert.watchlist_entry_id  # sanity: same entry throughout


async def test_update_alert_records_resolution_metadata(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="stolen")
    )
    detection = await ingest_detection(db_session, _detection_in())
    [alert] = await correlate_detection(db_session, detection)

    updated = await update_alert(
        db_session,
        alert.id,
        AlertUpdate(
            status="resolved", resolved_by="Insp. Test", resolution_note="Vehicle recovered"
        ),
    )

    assert updated is not None
    assert updated.status == "resolved"
    assert updated.resolved_by == "Insp. Test"
    assert updated.resolution_note == "Vehicle recovered"


async def test_update_alert_returns_none_for_an_unknown_id(db_session: AsyncSession) -> None:
    import uuid

    assert await update_alert(db_session, uuid.uuid4(), AlertUpdate(status="acknowledged")) is None


async def test_update_watchlist_entry_can_deactivate_and_reactivate(
    db_session: AsyncSession,
) -> None:
    entry = await create_watchlist_entry(
        db_session, WatchlistEntryCreate(plate="GJ01AB1234", entry_type="stolen")
    )

    deactivated = await update_watchlist_entry(db_session, entry.id, active=False)
    assert deactivated is not None
    assert deactivated.active is False

    reactivated = await update_watchlist_entry(db_session, entry.id, active=True)
    assert reactivated is not None
    assert reactivated.active is True


async def test_update_watchlist_entry_returns_none_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    import uuid

    assert await update_watchlist_entry(db_session, uuid.uuid4(), active=False) is None
