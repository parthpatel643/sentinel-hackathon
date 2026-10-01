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


def test_cameras_without_rtsp_or_marked_registry_only_are_not_opened() -> None:
    hls_only = _registry_camera(profiles=[{"protocol": "hls", "url": "http://x/y.m3u8"}])
    metadata_only = _registry_camera(tier=AnalyticsTier.D_REGISTRY_ONLY.value)

    assert _descriptor_from_registry(hls_only) is None
    assert _descriptor_from_registry(metadata_only) is None
    assert _descriptor_from_registry(_registry_camera(profiles=[])) is None


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
