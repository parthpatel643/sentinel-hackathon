"""Detection ingest/search/route tests against a real Postgres+Timescale
hypertable. See conftest.py for the transaction-rollback isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.detections.schemas import DetectionIn
from core_api.detections.service import (
    get_vehicle_route,
    ingest_detection,
    search_detections,
    within_one_edit,
)
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
    # A readable camera clock unless a test says otherwise; pass
    # camera_time=None for a sighting whose clock could not be read.
    defaults.setdefault("camera_time", defaults["observed_at"])
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
    """Liveness is our receipt time, not the frame's: replayed footage burns
    in a months-old clock, and using it would make a working camera stale."""
    await _make_camera(db_session)
    months_ago = ANCHOR - timedelta(days=100)
    detection = await ingest_detection(db_session, _detection_in(observed_at=months_ago))

    assert detection.id is not None
    assert detection.plate_normalised == "GJ01AB1234"
    assert detection.observed_at == months_ago

    camera = await get_camera(db_session, "det-cam-01")
    assert camera is not None
    assert camera.status == "live"
    assert camera.last_seen_at is not None
    assert datetime.now(UTC) - camera.last_seen_at < timedelta(minutes=1)


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

    The camera's clock is the only time a sighting is reported with, but it is
    only as good as the camera. Government feeds replay archived footage and
    report dates months old; a camera with a mis-set clock does the same.
    Window on it and the vehicle silently becomes unfindable precisely because
    one camera was wrong.
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
    # Processed now; the frame's clock says three months ago.
    await ingest_detection(
        db_session,
        _detection_in(
            event_id="01JEVTCLOCKDRIFT000000001",
            plate_text="GJ09ZZ9911",
            plate_normalised="GJ09ZZ9911",
            plate_ambiguity_key=ambiguity_key("GJ09ZZ9911"),
            observed_at=ANCHOR,
            camera_time=ANCHOR - timedelta(days=90),
        ),
    )

    route = await get_vehicle_route(db_session, "GJ09ZZ9911")

    assert len(route.points) == 1, "a stale camera clock must not hide a fresh sighting"
    # The time reported is exactly what the camera's clock said.
    assert route.points[0].camera_time == ANCHOR - timedelta(days=90)
    assert route.first_seen_at == ANCHOR - timedelta(days=90)


async def test_the_route_follows_the_cameras_clocks_not_processing_order(
    db_session: AsyncSession,
) -> None:
    """Footage is not processed in the order it was filmed — a replayed
    recording, a backlog, a second worker. The route is told in the order the
    cameras' clocks give."""
    await _make_camera(db_session, "det-cam-01")
    await _make_camera(db_session, "det-cam-02")
    await ingest_detection(
        db_session,
        _detection_in(
            event_id="evt-processed-first",
            camera_id="det-cam-02",
            observed_at=ANCHOR,
            camera_time=ANCHOR - timedelta(hours=2),
        ),
    )
    await ingest_detection(
        db_session,
        _detection_in(
            event_id="evt-processed-second",
            camera_id="det-cam-01",
            observed_at=ANCHOR + timedelta(minutes=1),
            camera_time=ANCHOR - timedelta(hours=3),
        ),
    )

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert [p.camera_id for p in route.points] == ["det-cam-01", "det-cam-02"]
    assert route.first_seen_at == ANCHOR - timedelta(hours=3)
    assert route.last_seen_at == ANCHOR - timedelta(hours=2)


async def test_a_sighting_with_an_unreadable_clock_is_kept_off_the_timed_route(
    db_session: AsyncSession,
) -> None:
    """Nothing stands in for the camera's clock. A sighting whose clock could
    not be read is still a sighting — counted and returned — but it has no
    place on a timeline, and no processing time is reported for it."""
    await _make_camera(db_session, "det-cam-01")
    await _make_camera(db_session, "det-cam-02")
    await ingest_detection(db_session, _detection_in(event_id="evt-timed", camera_id="det-cam-01"))
    await ingest_detection(
        db_session,
        _detection_in(
            event_id="evt-untimed",
            camera_id="det-cam-02",
            observed_at=ANCHOR + timedelta(minutes=5),
            camera_time=None,
        ),
    )

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert route.total_sightings == 2
    assert [p.event_id for p in route.points] == ["evt-timed"]
    assert [p.event_id for p in route.untimed] == ["evt-untimed"]
    assert route.untimed[0].camera_time is None
    assert route.last_seen_at == ANCHOR, "an untimed sighting has no time to be last at"
    serialised = route.model_dump(mode="json")
    assert "observed_at" not in serialised["untimed"][0]
    assert "observed_at" not in serialised["points"][0]


async def test_ingest_derives_search_keys_from_the_plate_text_not_the_producer(
    db_session: AsyncSession,
) -> None:
    """A third-party ANPR producer that sends its own (spaced, lower-case)
    'normalised' form must still be findable under the plate an operator
    types on evaluation day."""
    await _make_camera(db_session)
    detection = await ingest_detection(
        db_session,
        _detection_in(
            plate_text="gj 01 ab-1234",
            plate_normalised="gj 01 ab-1234",
            plate_ambiguity_key="whatever",
        ),
    )

    assert detection.plate_normalised == "GJ01AB1234"
    assert detection.plate_ambiguity_key == ambiguity_key("GJ01AB1234")
    route = await get_vehicle_route(db_session, "GJ 01 AB 1234")
    assert route.total_sightings == 1


def test_within_one_edit() -> None:
    assert within_one_edit("GJ01AB1234", "GJ01AB1234")
    assert within_one_edit("GJ01AB1234", "GJ01AB1284")  # substitution
    assert within_one_edit("GJ01AB1234", "GJ01AB234")  # dropped character
    assert within_one_edit("GJ01AB1234", "GJ01AAB1234")  # extra character
    assert not within_one_edit("GJ01AB1234", "GJ01AB1289")
    assert not within_one_edit("GJ01AB1234", "GJ01AB12")


async def test_route_falls_back_to_one_edit_reads_marked_probable(
    db_session: AsyncSession,
) -> None:
    """The designated plate misread at one camera by a character outside the
    ambiguity classes must still produce a route, but one the operator is
    told to confirm."""
    await _make_camera(db_session)
    await ingest_detection(db_session, _detection_in(plate_text="GJ01AB1284"))

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert route.total_sightings == 1
    assert route.points[0].match_rung == "edit_distance"
    assert route.points[0].confirmed is False
    assert route.points[0].plate_text == "GJ01AB1284"


async def test_one_edit_reads_never_dilute_an_exact_route(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    await ingest_detection(db_session, _detection_in())
    await ingest_detection(
        db_session, _detection_in(event_id="01JEVT0000000000000000002", plate_text="GJ01AB1235")
    )

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert [p.plate_text for p in route.points] == ["GJ01AB1234"]
    assert route.points[0].confirmed is True


async def test_short_queries_do_not_use_edit_distance(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    await ingest_detection(db_session, _detection_in(plate_text="AB1234"))

    route = await get_vehicle_route(db_session, "AB1235")

    assert route.total_sightings == 0


async def _camera_at(session: AsyncSession, camera_id: str, lat: float, lon: float) -> None:
    await upsert_camera(
        session,
        camera_id=camera_id,
        name=camera_id,
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=lat, lon=lon),
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )


async def _sighting(
    session: AsyncSession, n: int, camera_id: str, minutes: float, plate: str, colour: str = "white"
) -> None:
    await ingest_detection(
        session,
        _detection_in(
            event_id=f"01JBRIDGE{n:016d}",
            camera_id=camera_id,
            plate_text=plate,
            observed_at=ANCHOR - timedelta(hours=2) + timedelta(minutes=minutes),
            vehicle_class="car",
            vehicle_colour=colour,
        ),
    )


async def _three_junctions(session: AsyncSession) -> None:
    # ~3 km apart along a road, west to east.
    await _camera_at(session, "br-west", 23.0225, 72.5400)
    await _camera_at(session, "br-mid", 23.0225, 72.5700)
    await _camera_at(session, "br-east", 23.0225, 72.6000)


async def test_an_unreadable_middle_hop_is_bridged_as_probable(db_session: AsyncSession) -> None:
    await _three_junctions(db_session)
    await _sighting(db_session, 1, "br-west", 0, "GJ01AB1234")
    await _sighting(db_session, 2, "br-mid", 4, "MH01AB1234")  # state code misread
    await _sighting(db_session, 3, "br-east", 8, "GJ01AB1234")

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert [p.camera_id for p in route.points] == ["br-west", "br-mid", "br-east"]
    bridged = route.points[1]
    assert bridged.match_rung == "partial_attribute"
    assert bridged.confirmed is False
    assert bridged.plate_text == "MH01AB1234"
    assert not any(p.infeasible for p in route.points)
    assert route.points[2].implied_speed_kmh is not None
    assert 30 < route.points[2].implied_speed_kmh < 60


async def test_a_bridge_needs_matching_appearance_and_road_speed(db_session: AsyncSession) -> None:
    await _three_junctions(db_session)
    await _camera_at(db_session, "br-far", 21.1702, 72.8311)  # Surat, ~230 km away
    await _sighting(db_session, 1, "br-west", 0, "GJ01AB1234")
    await _sighting(db_session, 2, "br-mid", 4, "MH01AB1234", colour="red")
    await _sighting(db_session, 3, "br-far", 6, "GJ01AA1234")
    await _sighting(db_session, 4, "br-east", 8, "GJ01AB1234")

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert [p.camera_id for p in route.points] == ["br-west", "br-east"]


async def test_impossible_travel_between_exact_reads_is_flagged(db_session: AsyncSession) -> None:
    """Two exact reads 230 km apart in ten minutes: a cloned plate or a
    wrong camera clock, and an investigator must be told."""
    await _three_junctions(db_session)
    await _camera_at(db_session, "br-far", 21.1702, 72.8311)
    await _sighting(db_session, 1, "br-west", 0, "GJ01AB1234")
    await _sighting(db_session, 2, "br-far", 10, "GJ01AB1234")

    route = await get_vehicle_route(db_session, "GJ01AB1234")

    assert route.points[1].infeasible is True
    assert route.points[1].implied_speed_kmh is not None
    assert route.points[1].implied_speed_kmh > 1000
