"""Zone rules service tests against a real Postgres. See conftest.py for
the transaction-rollback isolation — nothing here is ever actually
persisted once a test ends."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import upsert_camera
from core_api.zones.schemas import ZoneCreate, ZoneEventIn
from core_api.zones.service import create_zone, list_zone_events, list_zones, record_zone_event

RIGHT_HALF = [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]


async def _make_camera(session: AsyncSession, camera_id: str = "zone-test-cam") -> None:
    await upsert_camera(
        session,
        camera_id=camera_id,
        name="Zone Test Camera",
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


async def test_create_zone_persists_the_polygon_and_rule_type(db_session: AsyncSession) -> None:
    await _make_camera(db_session)

    zone = await create_zone(
        db_session,
        "zone-test-cam",
        ZoneCreate(name="Restricted Area", rule_type="intrusion", polygon=RIGHT_HALF),
    )

    assert zone.camera_id == "zone-test-cam"
    assert zone.rule_type == "intrusion"
    assert zone.polygon == RIGHT_HALF
    assert zone.active is True


async def test_list_zones_only_returns_zones_for_the_requested_camera(
    db_session: AsyncSession,
) -> None:
    await _make_camera(db_session, "zone-test-cam-a")
    await _make_camera(db_session, "zone-test-cam-b")
    await create_zone(
        db_session,
        "zone-test-cam-a",
        ZoneCreate(name="Zone A", rule_type="intrusion", polygon=RIGHT_HALF),
    )
    await create_zone(
        db_session,
        "zone-test-cam-b",
        ZoneCreate(name="Zone B", rule_type="loitering", polygon=RIGHT_HALF),
    )

    zones_a = await list_zones(db_session, "zone-test-cam-a")

    assert len(zones_a) == 1
    assert zones_a[0].name == "Zone A"


async def test_an_inactive_zone_is_excluded_by_default(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    zone = await create_zone(
        db_session,
        "zone-test-cam",
        ZoneCreate(name="Old Zone", rule_type="intrusion", polygon=RIGHT_HALF),
    )
    zone.active = False
    await db_session.flush()

    active_zones = await list_zones(db_session, "zone-test-cam")
    all_zones = await list_zones(db_session, "zone-test-cam", active_only=False)

    assert active_zones == []
    assert len(all_zones) == 1


async def test_zone_create_rejects_an_unknown_rule_type() -> None:
    with pytest.raises(ValueError, match="rule_type"):
        ZoneCreate(name="Bad Zone", rule_type="teleportation", polygon=RIGHT_HALF)


async def test_zone_create_rejects_a_polygon_with_fewer_than_three_points() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        ZoneCreate(name="Bad Zone", rule_type="intrusion", polygon=[[0.0, 0.0], [1.0, 1.0]])


async def test_record_and_list_zone_events(db_session: AsyncSession) -> None:
    await _make_camera(db_session)
    zone = await create_zone(
        db_session,
        "zone-test-cam",
        ZoneCreate(name="Loading Bay", rule_type="loitering", polygon=RIGHT_HALF),
    )

    await record_zone_event(
        db_session,
        ZoneEventIn(
            zone_id=zone.id,
            camera_id="zone-test-cam",
            rule_type="loitering",
            track_id="42",
            dwell_time_s=15.0,
            observed_at=datetime.now(UTC),
        ),
    )

    pairs = await list_zone_events(db_session, camera_id="zone-test-cam")

    assert len(pairs) == 1
    event, zone_name = pairs[0]
    assert zone_name == "Loading Bay"
    assert event.track_id == "42"
    assert event.dwell_time_s == 15.0


async def test_list_zone_events_filters_by_camera(db_session: AsyncSession) -> None:
    await _make_camera(db_session, "zone-test-cam-a")
    await _make_camera(db_session, "zone-test-cam-b")
    zone_a = await create_zone(
        db_session,
        "zone-test-cam-a",
        ZoneCreate(name="Zone A", rule_type="intrusion", polygon=RIGHT_HALF),
    )
    zone_b = await create_zone(
        db_session,
        "zone-test-cam-b",
        ZoneCreate(name="Zone B", rule_type="intrusion", polygon=RIGHT_HALF),
    )
    now = datetime.now(UTC)
    await record_zone_event(
        db_session,
        ZoneEventIn(
            zone_id=zone_a.id,
            camera_id="zone-test-cam-a",
            rule_type="intrusion",
            track_id="1",
            observed_at=now,
        ),
    )
    await record_zone_event(
        db_session,
        ZoneEventIn(
            zone_id=zone_b.id,
            camera_id="zone-test-cam-b",
            rule_type="intrusion",
            track_id="2",
            observed_at=now,
        ),
    )

    pairs = await list_zone_events(db_session, camera_id="zone-test-cam-a")

    assert len(pairs) == 1
    assert pairs[0][0].camera_id == "zone-test-cam-a"
