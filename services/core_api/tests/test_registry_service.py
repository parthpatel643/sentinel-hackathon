"""Registry service tests against a real PostGIS-backed Postgres.

See conftest.py for the transaction-rollback isolation: nothing here is
ever actually persisted once a test ends.
"""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Camera, StreamProfile
from core_api.registry.schemas import CameraHealthUpdate, GeoPointOut, StreamProfileOut
from core_api.registry.service import (
    camera_to_out,
    codecs_in_use,
    get_camera,
    list_cameras,
    list_departments,
    resolve_camera_stream,
    update_camera_health,
    upsert_camera,
)
from sentinel_core.config import Settings


async def test_upsert_creates_a_new_camera(db_session: AsyncSession) -> None:
    camera = await upsert_camera(
        db_session,
        camera_id="cam-001",
        name="Junction Camera",
        driver_id="rtsp",
        department_name="Home Department",
        site_name="Sarkhej Circle",
        location=GeoPointOut(lat=23.0225, lon=72.5714),
        tier="a_continuous",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[StreamProfileOut(protocol="rtsp", url="rtsp://x/cam-001")],
    )

    assert camera.camera_id == "cam-001"
    assert camera.department is not None
    assert camera.department.name == "Home Department"
    assert camera.site is not None
    assert camera.site.name == "Sarkhej Circle"
    assert len(camera.profiles) == 1


async def test_upsert_is_idempotent_by_camera_id(db_session: AsyncSession) -> None:
    """Catalogue-driven onboarding re-runs the same batch on every sync — a
    camera seen twice must update in place, not duplicate."""
    await upsert_camera(
        db_session,
        camera_id="cam-002",
        name="Old Name",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="b_sampled",
        status="unknown",
        source="gov_catalogue",
        attributes={},
        profiles=[],
    )
    await upsert_camera(
        db_session,
        camera_id="cam-002",
        name="New Name",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="a_continuous",
        status="live",
        source="gov_catalogue",
        attributes={},
        profiles=[],
    )

    cameras = await list_cameras(db_session)
    matching = [c for c in cameras if c.camera_id == "cam-002"]
    assert len(matching) == 1
    assert matching[0].name == "New Name"
    assert matching[0].tier == "a_continuous"


async def test_upsert_replaces_stream_profiles_wholesale(db_session: AsyncSession) -> None:
    """A camera whose catalogue entry drops a protocol between syncs must
    lose that stale profile, not accumulate it forever."""
    await upsert_camera(
        db_session,
        camera_id="cam-003",
        name="Cam",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[
            StreamProfileOut(protocol="rtsp", url="rtsp://x/cam-003"),
            StreamProfileOut(protocol="hls", url="https://x/cam-003.m3u8"),
        ],
    )
    camera = await upsert_camera(
        db_session,
        camera_id="cam-003",
        name="Cam",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[StreamProfileOut(protocol="rtsp", url="rtsp://x/cam-003")],
    )

    assert {p.protocol for p in camera.profiles} == {"rtsp"}


async def test_get_camera_returns_none_for_an_unknown_id(db_session: AsyncSession) -> None:
    assert await get_camera(db_session, "does-not-exist") is None


async def test_location_round_trips_through_postgis(db_session: AsyncSession) -> None:
    """The whole point of using a real Geometry column: a lat/lon in, the
    same lat/lon out, via actual PostGIS storage, not a mock."""
    camera = await upsert_camera(
        db_session,
        camera_id="cam-004",
        name="Cam",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=23.0225, lon=72.5714),
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )

    out = camera_to_out(camera)
    assert out.location is not None
    assert abs(out.location.lat - 23.0225) < 1e-6
    assert abs(out.location.lon - 72.5714) < 1e-6


async def test_department_camera_count_reflects_assigned_cameras(db_session: AsyncSession) -> None:
    await upsert_camera(
        db_session,
        camera_id="cam-005",
        name="Cam",
        driver_id="rtsp",
        department_name="GSRTC",
        site_name=None,
        location=None,
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )
    await upsert_camera(
        db_session,
        camera_id="cam-006",
        name="Cam",
        driver_id="rtsp",
        department_name="GSRTC",
        site_name=None,
        location=None,
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )

    departments = await list_departments(db_session)
    gsrtc = next(d for d in departments if d.name == "GSRTC")
    assert gsrtc.camera_count == 2


async def test_list_cameras_filters_by_department(db_session: AsyncSession) -> None:
    await upsert_camera(
        db_session,
        camera_id="cam-007",
        name="Cam",
        driver_id="rtsp",
        department_name="Food & Civil Supplies",
        site_name=None,
        location=None,
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )
    await upsert_camera(
        db_session,
        camera_id="cam-008",
        name="Cam",
        driver_id="rtsp",
        department_name="RTO",
        site_name=None,
        location=None,
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )

    filtered = await list_cameras(db_session, department_name="RTO")
    assert [c.camera_id for c in filtered] == ["cam-008"]


async def test_attributes_round_trip_as_a_json_dict(db_session: AsyncSession) -> None:
    camera = await upsert_camera(
        db_session,
        camera_id="cam-009",
        name="Cam",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="b_sampled",
        status="unknown",
        source="manual",
        attributes={"mount": "pole", "height_m": "6"},
        profiles=[],
    )

    assert camera.attributes == {"mount": "pole", "height_m": "6"}


async def test_codecs_in_use_only_counts_live_cameras(db_session: AsyncSession) -> None:
    """Backs the Integrator Compliance panel's mixed-codec-handling tick —
    proof by observation, so a camera that is down (and hasn't produced a
    frame recently) must not count towards the "we handle codec X" claim."""
    await upsert_camera(
        db_session,
        camera_id="cam-010",
        name="Live h264",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="b_sampled",
        status="live",
        source="manual",
        attributes={},
        profiles=[StreamProfileOut(protocol="rtsp", url="rtsp://x/cam-010", codec="h264")],
    )
    await upsert_camera(
        db_session,
        camera_id="cam-011",
        name="Live h265",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="b_sampled",
        status="live",
        source="manual",
        attributes={},
        profiles=[StreamProfileOut(protocol="rtsp", url="rtsp://x/cam-011", codec="h265")],
    )
    await upsert_camera(
        db_session,
        camera_id="cam-012",
        name="Down mpeg4",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="b_sampled",
        status="down",
        source="manual",
        attributes={},
        profiles=[StreamProfileOut(protocol="rtsp", url="rtsp://x/cam-012", codec="mpeg4")],
    )

    codecs = await codecs_in_use(db_session)

    assert codecs == ["h264", "h265"]


async def test_update_camera_health_persists_tamper_status(db_session: AsyncSession) -> None:
    await upsert_camera(
        db_session,
        camera_id="tamper-cam-01",
        name="Tamper Test Camera",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="a_continuous",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )

    updated = await update_camera_health(
        db_session,
        "tamper-cam-01",
        CameraHealthUpdate(status="live", tamper_status="covered"),
    )

    assert updated is not None
    assert updated.tamper_status == "covered"
    assert camera_to_out(updated).tamper_status == "covered"


async def test_update_camera_health_without_tamper_status_leaves_it_unchanged(
    db_session: AsyncSession,
) -> None:
    """A heartbeat that omits tamper_status (e.g. a driver that hasn't
    wired tamper detection at all) must not stomp the last known value —
    same "only touch what's reported" contract as measured_fps/reconnects."""
    await upsert_camera(
        db_session,
        camera_id="tamper-cam-02",
        name="Tamper Test Camera 2",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=None,
        tier="a_continuous",
        status="unknown",
        source="manual",
        attributes={},
        profiles=[],
    )
    await update_camera_health(
        db_session, "tamper-cam-02", CameraHealthUpdate(status="live", tamper_status="blurred")
    )

    updated = await update_camera_health(
        db_session, "tamper-cam-02", CameraHealthUpdate(status="live")
    )

    assert updated is not None
    assert updated.tamper_status == "blurred"


def _camera_with_rtsp(camera_id: str, rtsp_url: str, status: str = "live") -> Camera:
    """A plain, unpersisted ORM instance — resolve_camera_stream only ever
    reads `camera.camera_id`/`camera.profiles`/`camera.status`, so no DB
    round-trip is needed to exercise it."""
    camera = Camera(camera_id=camera_id, name=camera_id, driver_id="rtsp", status=status)
    camera.profiles = [StreamProfile(camera_id=camera_id, protocol="rtsp", url=rtsp_url)]
    return camera


async def test_resolve_camera_stream_refuses_a_camera_that_is_down() -> None:
    """A relay path can exist while carrying no video — that is exactly what
    happens when the upstream gateway drops. Handing the browser an HLS URL
    then leaves the tile on "Connecting…" forever, so a camera the worker has
    marked `down` must be reported unavailable, with a reason, instead."""
    settings = Settings(relay_rtsp_url="rtsp://localhost:8554", relay_hls_url="http://localhost:8888")
    camera = _camera_with_rtsp("cam06", "rtsp://gateway.example/cam06", status="down")

    async def _unexpected_call(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"should not touch the relay for a down camera: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(_unexpected_call))
    result = await resolve_camera_stream(camera, settings, client=client)
    await client.aclose()

    assert result.available is False
    assert result.hls_url is None
    assert result.reason is not None and "isn't sending video" in result.reason


async def test_resolve_camera_stream_still_serves_an_unknown_camera() -> None:
    """`unknown` is "nobody has looked yet", not "broken". Those paths are
    served on demand and connect on first view, so they must not be caught by
    the `down` guard above."""
    settings = Settings(relay_rtsp_url="rtsp://localhost:8554", relay_hls_url="http://localhost:8888")
    camera = _camera_with_rtsp("cam18", "rtsp://localhost:8554/dev/cam18", status="unknown")

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    result = await resolve_camera_stream(camera, settings, client=client)
    await client.aclose()

    assert result.available is True


async def test_resolve_camera_stream_resolves_our_own_relay_directly() -> None:
    """A synthetic-grid camera's RTSP host matches relay_rtsp_url — no
    MediaMTX API call should even be attempted."""
    settings = Settings(relay_rtsp_url="rtsp://localhost:8554", relay_hls_url="http://localhost:8888")
    camera = _camera_with_rtsp("dev-cam-01", "rtsp://localhost:8554/dev/dev-cam-01")

    async def _unexpected_call(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"should never call the relay API for a local camera: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(_unexpected_call))
    result = await resolve_camera_stream(camera, settings, client=client)
    await client.aclose()

    assert result.available is True
    assert result.hls_url == "http://localhost:8888/dev/dev-cam-01/index.m3u8"


async def test_resolve_camera_stream_proxies_an_external_camera_via_relay_pull() -> None:
    """A gov-catalogue camera's RTSP host doesn't match our relay — the path
    doesn't exist yet, so it must be added as a PULL source."""
    settings = Settings(relay_rtsp_url="rtsp://localhost:8554", relay_hls_url="http://localhost:8888")
    camera = _camera_with_rtsp("cam01", "rtsp://user:pass@103.250.160.189:8554/stream/cam01")
    calls: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(404)
        assert request.method == "POST"
        assert str(request.url).endswith("/v3/config/paths/add/ext/cam01")
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    result = await resolve_camera_stream(camera, settings, client=client)
    await client.aclose()

    assert result.available is True
    assert result.hls_url == "http://localhost:8888/ext/cam01/index.m3u8"
    assert [c.method for c in calls] == ["GET", "POST"]


async def test_resolve_camera_stream_reuses_an_already_registered_relay_path() -> None:
    """If the path was already added (a previous preview request, or a
    concurrent one), no POST should be attempted at all."""
    settings = Settings(relay_rtsp_url="rtsp://localhost:8554", relay_hls_url="http://localhost:8888")
    camera = _camera_with_rtsp("cam02", "rtsp://user:pass@103.250.160.189:8554/stream/cam02")

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method != "POST", "an existing path must never be re-added"
        assert request.method == "GET"
        return httpx.Response(200, json={"name": "ext/cam02", "sourceOnDemand": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    result = await resolve_camera_stream(camera, settings, client=client)
    await client.aclose()

    assert result.available is True
    assert result.hls_url == "http://localhost:8888/ext/cam02/index.m3u8"


async def test_resolve_camera_stream_treats_a_racing_duplicate_add_as_success() -> None:
    """Two concurrent first-time previews can both see the path missing and
    both attempt to add it — MediaMTX's 400 'already exists' on the loser is
    the desired end state, not a failure."""
    settings = Settings(relay_rtsp_url="rtsp://localhost:8554", relay_hls_url="http://localhost:8888")
    camera = _camera_with_rtsp("cam03", "rtsp://user:pass@103.250.160.189:8554/stream/cam03")

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(400, json={"status": "error", "error": "path already exists"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    result = await resolve_camera_stream(camera, settings, client=client)
    await client.aclose()

    assert result.available is True


async def test_resolve_camera_stream_reports_unavailable_when_the_relay_is_unreachable() -> None:
    """A MediaMTX outage must degrade to 'preview unavailable', never a 500
    on the whole Cameras screen."""
    settings = Settings(relay_rtsp_url="rtsp://localhost:8554", relay_hls_url="http://localhost:8888")
    camera = _camera_with_rtsp("cam04", "rtsp://user:pass@103.250.160.189:8554/stream/cam04")

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    result = await resolve_camera_stream(camera, settings, client=client)
    await client.aclose()

    assert result.available is False
    assert result.reason is not None and "relay" in result.reason.lower()


async def test_resolve_camera_stream_reports_no_rtsp_profile() -> None:
    settings = Settings()
    camera = Camera(camera_id="cam05", name="cam05", driver_id="rtsp")
    camera.profiles = []

    result = await resolve_camera_stream(camera, settings)

    assert result.available is False
    assert result.reason == "This camera has no RTSP profile on file."
