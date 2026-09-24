"""Detection ingest/search/route tests against a real Postgres+Timescale
hypertable. See conftest.py for the transaction-rollback isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.detections.schemas import DetectionIn
from core_api.detections.service import get_vehicle_route, ingest_detection, search_detections
from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import get_camera, upsert_camera
from sentinel_core.plates import ambiguity_key

# get_vehicle_route only looks back 24h by default — anchored to real "now",
# not a fixed calendar date, so these tests stay valid regardless of when
# they run.
ANCHOR = datetime.now(UTC).replace(microsecond=0)


def _detection_in(**overrides: object) -> DetectionIn:
    defaults: dict[str, object] = {
        "event_id": "01JEVT0000000000000000001",
        "camera_id": "det-cam-01",
        "plate_text": "GJ01AB1234",
        "plate_normalised": "GJ01AB1234",
        "plate_ambiguity_key": "GJ01AB1234",
        "plate_confidence": 0.9,
        "pts_ms": 1000.0,
        "observed_at": ANCHOR,
        "node_id": "edge-local-01",
    }
    defaults.update(overrides)
    return DetectionIn.model_validate(defaults)


async def _make_camera(session: AsyncSession, camera_id: str = "det-cam-01") -> None:
    await upsert_camera(
        session,
        camera_id=camera_id,
        name="Detections Test Camera",
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


async def test_ingest_detection_persists_and_marks_camera_live(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    detection = await ingest_detection(db_session, _detection_in())

    assert detection.id is not None
    assert detection.plate_normalised == "GJ01AB1234"

    camera = await get_camera(db_session, "det-cam-01")
    assert camera is not None
    assert camera.status == "live"
    assert camera.last_seen_at == ANCHOR


async def test_search_detections_filters_by_plate(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    await ingest_detection(db_session, _detection_in(event_id="evt-1", plate_text="GJ01AB1234"))
    await ingest_detection(
        db_session,
        _detection_in(
            event_id="evt-2",
            plate_text="GJ05CD9999",
            plate_normalised="GJ05CD9999",
            plate_ambiguity_key="GJ05CD9999",
        ),
    )

    results = await search_detections(db_session, plate="GJ01AB1234")
    assert [r.event_id for r in results] == ["evt-1"]


async def test_search_detections_filters_by_camera_and_time_window(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session, "det-cam-01")
    await _make_camera(db_session, "det-cam-02")
    await ingest_detection(
        db_session, _detection_in(event_id="evt-early", camera_id="det-cam-01", observed_at=ANCHOR)
    )
    later = ANCHOR + timedelta(hours=1)
    await ingest_detection(
        db_session,
        _detection_in(event_id="evt-late", camera_id="det-cam-02", observed_at=later),
    )

    by_camera = await search_detections(db_session, camera_id="det-cam-02")
    assert [r.event_id for r in by_camera] == ["evt-late"]

    by_window = await search_detections(db_session, since=ANCHOR + timedelta(minutes=30))
    assert [r.event_id for r in by_window] == ["evt-late"]


async def test_vehicle_route_reconstructs_ordered_sightings_across_cameras(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session, "det-cam-01")
    await _make_camera(db_session, "det-cam-02")
    await ingest_detection(
        db_session,
        _detection_in(event_id="evt-1", camera_id="det-cam-01", observed_at=ANCHOR),
    )
    later = ANCHOR + timedelta(hours=1)
    await ingest_detection(
        db_session,
        _detection_in(event_id="evt-2", camera_id="det-cam-02", observed_at=later),
    )

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert route.total_sightings == 2
    assert [p.camera_id for p in route.points] == ["det-cam-01", "det-cam-02"]
    assert route.first_seen_at == ANCHOR
    assert route.last_seen_at == later


async def test_vehicle_route_falls_back_to_ambiguity_class_when_no_exact_match(
    db_session: AsyncSession,
) -> None:
    """A plate read as "GJ014B1234" (OCR misreads the "A" as the digit "4" —
    both fold to the same ambiguity class) must still surface a route for
    someone searching the correct "GJ01AB1234"."""
    misread_text = "GJ014B1234"
    await _make_camera(db_session)
    await ingest_detection(
        db_session,
        _detection_in(
            event_id="evt-ambiguous",
            plate_text=misread_text,
            plate_normalised=misread_text,
            plate_ambiguity_key=ambiguity_key(misread_text),
        ),
    )

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert route.total_sightings == 1
    assert route.points[0].match_rung == "ambiguity_class"
    assert route.points[0].plate_text == misread_text


async def test_vehicle_route_is_empty_for_a_plate_never_seen(db_session: AsyncSession) -> None:
    route = await get_vehicle_route(db_session, "GJ99ZZ0000")
    assert route.total_sightings == 0
    assert route.points == []
    assert route.first_seen_at is None


async def test_a_route_is_found_even_when_the_camera_clock_is_badly_wrong(
    db_session: AsyncSession,
) -> None:
    """The search window is measured against our own clock, not the camera's.

    `observed_at` carries the time burned into the frame, which is the scene's
    time and belongs in evidence — but it is only as good as the camera that
    produced it. Government feeds replay archived footage and report dates
    months old; a camera with a mis-set clock does the same, and that is
    routine across a large estate. Window on that and the vehicle silently
    becomes unfindable precisely because one camera was wrong, which is the
    opposite of what an operator asking "seen in the last 24 hours" wants.
    """
    await upsert_camera(
        db_session,
        camera_id="det-cam-01",
        name="Clock Drift Camera",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=23.0225, lon=72.5714),
        tier="a_continuous",
        status="live",
        source="manual",
        attributes={},
        profiles=[],
    )
    # Ingested now; the frame claims it happened three months ago.
    await ingest_detection(
        db_session,
        _detection_in(
            event_id="01JEVTCLOCKDRIFT000000001",
            plate_text="GJ09ZZ9911",
            plate_normalised="GJ09ZZ9911",
            plate_ambiguity_key=ambiguity_key("GJ09ZZ9911"),
            observed_at=ANCHOR - timedelta(days=90),
        ),
    )

    route = await get_vehicle_route(db_session, "GJ09ZZ9911")

    assert len(route.points) == 1, "a stale camera clock must not hide a fresh sighting"
    # The evidence timestamp itself is left exactly as the camera reported it.
    assert route.points[0].observed_at == ANCHOR - timedelta(days=90)
