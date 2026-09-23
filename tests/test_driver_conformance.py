"""Driver conformance suite — docs/01-ARCHITECTURE.md section 4.1: "A driver
conformance test suite (pytest contract tests) runs against every driver,
including the mocks — this is the evidence that the plugin SDK is real."

The same contract checks run against every concrete `CameraSource`
implementation via `pytest.mark.parametrize`, each backed by a mock/fake
double rather than a live camera so this suite runs anywhere. Adding driver
#3 means adding one more entry to `_DRIVER_CASES` below — that's the whole
point of the interface.

The ONVIF mock here is deliberately a smaller, self-contained copy of
packages/sentinel_core/tests/fixtures/mock_onvif_server.py rather than an
import of it: a `tests/` directory isn't part of any installed package
(there is no packages/sentinel_core/tests/__init__.py chain reachable from
the repo root), so cross-package test-fixture imports aren't reliable here
— this suite only needs discover()/health() to work, not the full protocol
surface the ONVIF-specific test file already covers in detail.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

import httpx
import numpy as np
import pytest

from edge_agent.adapters.rtsp_driver import RtspSource
from sentinel_core.drivers.base import CameraSource, DiscoveryScope
from sentinel_core.drivers.onvif import OnvifSource
from sentinel_core.schemas.camera import CameraStatus

_MOCK_ONVIF_NS = {"soap": "http://www.w3.org/2003/05/soap-envelope"}


def _mock_onvif_handler(request: httpx.Request) -> httpx.Response:
    """The bare minimum for discover()/health() to succeed: every request
    gets a canned, successful response keyed off the operation's local
    name. Auth digest correctness is exercised in the dedicated ONVIF
    driver test file, not re-verified here."""
    root = ET.fromstring(request.content)
    body = root.find(".//soap:Body", _MOCK_ONVIF_NS)
    operation = body[0].tag.split("}")[-1] if body is not None and len(body) else ""

    ns = (
        'xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
        'xmlns:trt="http://www.onvif.org/ver10/media/wsdl"'
    )
    if operation == "GetDeviceInformation":
        inner = (
            "<tds:GetDeviceInformationResponse>"
            "<tds:Manufacturer>ConformanceVendor</tds:Manufacturer>"
            "<tds:Model>ConformanceCam</tds:Model>"
            "<tds:SerialNumber>CONFORMANCE-001</tds:SerialNumber>"
            "</tds:GetDeviceInformationResponse>"
        )
    elif operation == "GetProfiles":
        inner = (
            '<trt:GetProfilesResponse><trt:Profiles token="P1">'
            "<trt:Name>Main</trt:Name></trt:Profiles></trt:GetProfilesResponse>"
        )
    elif operation == "GetStreamUri":
        inner = (
            "<trt:GetStreamUriResponse><trt:MediaUri>"
            "<trt:Uri>rtsp://127.0.0.1:8554/conformance/profile1</trt:Uri>"
            "</trt:MediaUri></trt:GetStreamUriResponse>"
        )
    else:
        inner = f"<tds:{operation}Response/>"

    envelope = (
        f'<?xml version="1.0"?><soap:Envelope {ns}><soap:Body>{inner}</soap:Body></soap:Envelope>'
    )
    return httpx.Response(
        200, content=envelope.encode(), headers={"Content-Type": "application/soap+xml"}
    )


@dataclass
class _FakeVideoSource:
    """A minimal, self-contained VideoSource double — deliberately not
    importing edge_agent's own test-only fakes.py, so this cross-package
    suite has no import-path dependency on another package's tests/
    directory (which isn't installed or guaranteed to be on sys.path)."""

    should_open: bool = True
    _opened: bool = field(default=False, init=False)

    def isOpened(self) -> bool:  # noqa: N802 - matches cv2's naming
        return self._opened

    def read(self) -> tuple[bool, np.ndarray | None]:
        if not self._opened:
            return False, None
        return True, np.zeros((48, 64, 3), dtype=np.uint8)

    def get(self, prop_id: int) -> float:
        return 25.0 if prop_id == 5 else 0.0  # 5 == cv2.CAP_PROP_FPS

    def set(self, prop_id: int, value: float) -> bool:
        return True

    def release(self) -> None:
        self._opened = False

    def _open(self) -> None:
        self._opened = self.should_open


def _rtsp_backend_factory(source: _FakeVideoSource) -> Callable[[str], _FakeVideoSource]:
    def factory(_url: str) -> _FakeVideoSource:
        source._open()
        return source

    return factory


def _make_onvif_source() -> OnvifSource:
    return OnvifSource(
        username="admin", password="pass", transport=httpx.MockTransport(_mock_onvif_handler)
    )


def _make_rtsp_source() -> RtspSource:
    return RtspSource(backend_factory=_rtsp_backend_factory(_FakeVideoSource(should_open=True)))


@dataclass
class DriverCase:
    """One driver under test plus the scope that reaches its mock/fake."""

    name: str
    make_source: Callable[[], CameraSource]
    scope: DiscoveryScope


_DRIVER_CASES = [
    DriverCase("onvif", _make_onvif_source, DiscoveryScope(host="mock-cam")),
    DriverCase("rtsp", _make_rtsp_source, DiscoveryScope(host="rtsp://fake-camera/stream1")),
]


@pytest.mark.parametrize("case", _DRIVER_CASES, ids=lambda c: c.name)
async def test_discover_returns_at_least_one_camera_with_a_stream_profile(case: DriverCase) -> None:
    source = case.make_source()

    descriptors = await source.discover(case.scope)

    assert len(descriptors) >= 1
    descriptor = descriptors[0]
    assert descriptor.driver_id == source.driver_id
    assert len(descriptor.profiles) >= 1
    assert all(profile.url for profile in descriptor.profiles)


@pytest.mark.parametrize("case", _DRIVER_CASES, ids=lambda c: c.name)
async def test_discover_with_an_empty_scope_never_raises(case: DriverCase) -> None:
    """Every driver must degrade gracefully (empty list), never throw, when
    asked to discover with nothing to go on — a caller looping over
    multiple drivers can't be expected to special-case each one."""
    source = case.make_source()

    descriptors = await source.discover(DiscoveryScope(host=None, timeout_s=0.1))

    assert isinstance(descriptors, list)


@pytest.mark.parametrize("case", _DRIVER_CASES, ids=lambda c: c.name)
async def test_health_of_a_discovered_camera_is_live(case: DriverCase) -> None:
    source = case.make_source()
    descriptors = await source.discover(case.scope)
    assert descriptors, f"{case.name} driver produced no descriptor to health-check"

    health = await source.health(descriptors[0])

    assert health.status is CameraStatus.LIVE


@pytest.mark.parametrize("case", _DRIVER_CASES, ids=lambda c: c.name)
async def test_open_returns_a_stream_handle_matching_the_profile(case: DriverCase) -> None:
    source = case.make_source()
    descriptors = await source.discover(case.scope)
    assert descriptors
    profile = descriptors[0].profiles[0]

    handle = await source.open(descriptors[0], profile)

    assert handle.url == profile.url
    assert handle.protocol == profile.protocol


@pytest.mark.parametrize("case", _DRIVER_CASES, ids=lambda c: c.name)
def test_capabilities_are_declared_not_assumed(case: DriverCase) -> None:
    """The UI's capability matrix (docs/01-ARCHITECTURE.md §4.1) reads this
    directly — every driver must actually set it, not inherit a silent
    default that overclaims what it can do."""
    source = case.make_source()

    assert source.capabilities.live is True
