"""`--source registry`: turning the core API's camera registry into the
worker's camera list — the path every camera onboarded on site takes."""

from __future__ import annotations

from typing import Any

import httpx

from edge_agent.worker import (
    _descriptor_from_registry,
    _fetch_registry_descriptors,
    _select_cameras,
)
from sentinel_core.schemas import AnalyticsTier, StreamProtocol

CREDENTIALED = "rtsp://admin:p%40ss@10.20.1.15:554/Streaming/Channels/101"


def _registry_camera(**overrides: Any) -> dict[str, Any]:
    return {
        "camera_id": "gsrtc-depot-01",
        "name": "Depot gate",
        "driver_id": "hikvision",
        "department_name": "GSRTC",
        "site_name": "Geeta Mandir depot",
        "location": {"lat": 23.01, "lon": 72.59},
        "tier": "b_sampled",
        "attributes": {"source": "bulk_csv"},
        "profiles": [
            {"protocol": "RTSP", "url": CREDENTIALED, "codec": "h265", "width": 2560},
            {"protocol": "hls", "url": "http://10.20.1.15/live.m3u8"},
            {"protocol": "vendor-sdk", "url": "sdk://whatever"},
        ],
    } | overrides


def test_a_registry_camera_keeps_its_credentialed_url_and_metadata() -> None:
    descriptor = _descriptor_from_registry(_registry_camera())

    assert descriptor is not None
    rtsp = descriptor.profile_for(StreamProtocol.RTSP)
    assert rtsp is not None and rtsp.url == CREDENTIALED
    assert rtsp.codec == "h265"
    assert descriptor.department == "GSRTC"
    assert descriptor.location is not None and descriptor.location.lat == 23.01
    # An unknown protocol is skipped rather than failing the whole camera.
    assert [p.protocol for p in descriptor.profiles] == [StreamProtocol.RTSP, StreamProtocol.HLS]


def test_cameras_with_nothing_to_open_or_marked_registry_only_are_skipped() -> None:
    whep_only = _registry_camera(profiles=[{"protocol": "whep", "url": "http://x/whep"}])
    metadata_only = _registry_camera(tier=AnalyticsTier.D_REGISTRY_ONLY.value)

    assert _descriptor_from_registry(whep_only) is None
    assert _descriptor_from_registry(metadata_only) is None
    assert _descriptor_from_registry(_registry_camera(profiles=[])) is None


def test_an_hls_only_camera_is_still_analysed() -> None:
    """A department that exposes only HLS (or a network that blocks RTSP)
    must not drop out of analysis."""
    hls_only = _registry_camera(profiles=[{"protocol": "hls", "url": "http://x/y.m3u8"}])

    descriptor = _descriptor_from_registry(hls_only)

    assert descriptor is not None
    assert descriptor.profile_for(StreamProtocol.HLS) is not None


def test_missing_location_and_odd_tier_are_tolerated() -> None:
    descriptor = _descriptor_from_registry(_registry_camera(location=None, tier="custom"))

    assert descriptor is not None
    assert descriptor.location is None
    assert descriptor.tier is AnalyticsTier.B_SAMPLED


async def test_the_manifest_is_read_with_the_service_token_client() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["token"] = request.headers.get("x-service-token", "")
        return httpx.Response(
            200,
            json=[
                _registry_camera(),
                _registry_camera(camera_id="meta-only", tier="d_registry_only"),
            ],
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://api",
        headers={"X-Service-Token": "svc"},
    ) as client:
        descriptors = await _fetch_registry_descriptors(client)

    assert seen == {"path": "/api/v1/edge/cameras", "token": "svc"}
    assert [d.camera_id for d in descriptors] == ["gsrtc-depot-01"]


def test_selection_by_department_ids_and_limit() -> None:
    cameras = [
        d
        for d in (
            _descriptor_from_registry(_registry_camera(camera_id="p1", department_name="Police")),
            _descriptor_from_registry(_registry_camera(camera_id="p2", department_name="police")),
            _descriptor_from_registry(_registry_camera(camera_id="g1", department_name="GSRTC")),
        )
        if d is not None
    ]

    assert [d.camera_id for d in _select_cameras(cameras, cameras=None, limit=None)] == [
        "p1",
        "p2",
        "g1",
    ]
    by_department = _select_cameras(cameras, cameras=None, limit=None, department="POLICE")
    assert [d.camera_id for d in by_department] == ["p1", "p2"]
    assert [d.camera_id for d in _select_cameras(cameras, cameras="g1,p2", limit=1)] == [
        "p2",
        "g1",
    ]
    assert [d.camera_id for d in _select_cameras(cameras, cameras=None, limit=1)] == ["p1"]


def test_load_meter_reports_analysed_frames_per_stream_second() -> None:
    from datetime import UTC, datetime, timedelta

    from edge_agent.worker import _LoadMeter
    from sentinel_core.clock import FrameTiming

    epoch = datetime(2026, 10, 12, tzinfo=UTC)

    def timing(seq: int, pts_ms: float) -> FrameTiming:
        return FrameTiming(
            camera_id="c",
            pts_ms=pts_ms,
            seq=seq,
            stream_epoch=epoch,
            observed_at=epoch + timedelta(milliseconds=pts_ms),
            delta_ms=40.0,
            is_gap=False,
            is_discontinuity=False,
        )

    meter = _LoadMeter()
    for i in range(126):  # 5 s of a 25 fps stream, every third frame analysed
        meter.saw(timing(i, i * 40.0))
        if i % 3 == 0:
            meter.analysed()

    rate = meter.take_analysed_fps()

    assert rate is not None and 8.0 <= rate <= 8.7
    assert meter.latest is not None
    assert meter.latest.observed_at == epoch + timedelta(seconds=5)
