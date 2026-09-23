"""What the worker actually opens for a camera.

The whole point of routing analytics through the local relay is that the
government gateway sees one connection per camera instead of one per
consumer. That is invisible in normal operation and only shows up as a
metered quota running out twice as fast, so it is pinned down here.
"""

from __future__ import annotations

import httpx
import pytest

from edge_agent.worker import _resolve_capture_url
from sentinel_core.config import Settings
from sentinel_core.schemas import (
    AnalyticsTier,
    CameraDescriptor,
    CameraStatus,
    SourceCapabilities,
    StreamProfile,
    StreamProtocol,
)

GOV_URL = "rtsp://user:pass@103.250.160.189:8554/stream/cam01"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        relay_rtsp_url="rtsp://localhost:8554",
        relay_api_url="http://localhost:9997",
    )


def _descriptor(camera_id: str, url: str) -> CameraDescriptor:
    return CameraDescriptor(
        camera_id=camera_id,
        name=camera_id,
        driver_id="rtsp",
        profiles=[StreamProfile(protocol=StreamProtocol.RTSP, url=url)],
        capabilities=SourceCapabilities(live=True, snapshot=False, playback=False),
        tier=AnalyticsTier.B_SAMPLED,
        status=CameraStatus.UNKNOWN,
    )


async def test_an_external_camera_is_read_through_the_local_relay(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def fake_ensure(**kwargs: object) -> bool:
        calls.append(str(kwargs["path_name"]))
        assert kwargs["rtsp_url"] == GOV_URL
        # A permanent reader must not let its path tear down between
        # reconnects, or every recovery re-dials the gateway.
        assert kwargs["on_demand"] is False
        return True

    monkeypatch.setattr("edge_agent.worker.ensure_relay_path", fake_ensure)

    url = await _resolve_capture_url(_descriptor("cam01", GOV_URL), settings, via_relay=True)

    assert url == "rtsp://localhost:8554/ext/cam01"
    assert calls == ["ext/cam01"]
    assert GOV_URL not in (url or ""), "the camera's credentialed URL must not be what we open"


async def test_a_synthetic_camera_is_not_republished_through_itself(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The synthetic grid already publishes into this relay. Registering it
    as a pull source would point the relay at itself."""

    async def fail(**_: object) -> bool:
        raise AssertionError("a relay-hosted camera must never be re-registered")

    monkeypatch.setattr("edge_agent.worker.ensure_relay_path", fail)

    local = "rtsp://127.0.0.1:8554/dev/dev-cam-01"
    url = await _resolve_capture_url(_descriptor("dev-cam-01", local), settings, via_relay=True)

    assert url == local


async def test_direct_mode_bypasses_the_relay_entirely(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(**_: object) -> bool:
        raise AssertionError("--direct must not touch the relay")

    monkeypatch.setattr("edge_agent.worker.ensure_relay_path", fail)

    url = await _resolve_capture_url(_descriptor("cam01", GOV_URL), settings, via_relay=False)

    assert url == GOV_URL


async def test_a_relay_failure_falls_back_to_the_camera_with_a_warning(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Better a degraded demo than a dead one — but the fallback doubles the
    gateway connections for any previewed camera, so it must be loud."""

    async def unavailable(**_: object) -> bool:
        return False

    monkeypatch.setattr("edge_agent.worker.ensure_relay_path", unavailable)

    with caplog.at_level("WARNING"):
        url = await _resolve_capture_url(_descriptor("cam01", GOV_URL), settings, via_relay=True)

    assert url == GOV_URL
    assert "SECOND connection" in caplog.text


async def test_a_camera_with_no_rtsp_profile_resolves_to_nothing(settings: Settings) -> None:
    descriptor = CameraDescriptor(
        camera_id="cam99",
        name="cam99",
        driver_id="rtsp",
        profiles=[StreamProfile(protocol=StreamProtocol.HLS, url="http://x/index.m3u8")],
        capabilities=SourceCapabilities(live=True, snapshot=False, playback=False),
        tier=AnalyticsTier.B_SAMPLED,
        status=CameraStatus.UNKNOWN,
    )
    assert await _resolve_capture_url(descriptor, settings, via_relay=True) is None


async def test_the_relay_registration_uses_a_real_http_client(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the real `ensure_relay_path`, with only the
    transport faked — so a change to the MediaMTX call shape is caught here
    rather than in a live run."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def patched(**kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("edge_agent.worker.httpx.AsyncClient", patched)

    url = await _resolve_capture_url(_descriptor("cam01", GOV_URL), settings, via_relay=True)

    assert url == "rtsp://localhost:8554/ext/cam01"
    assert [r.method for r in requests] == ["GET", "POST"]
    assert str(requests[1].url).endswith("/v3/config/paths/add/ext/cam01")
