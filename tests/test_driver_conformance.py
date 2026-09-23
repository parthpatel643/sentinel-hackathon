"""Driver conformance suite — docs/01-ARCHITECTURE.md section 4.1: "A driver
conformance test suite (pytest contract tests) runs against every driver,
including the mocks — this is the evidence that the plugin SDK is real."

The same contract checks run against every concrete `CameraSource`
implementation via `pytest.mark.parametrize`, each backed by a mock/fake
double rather than a live camera so this suite runs anywhere. Adding driver
#3 means adding one more entry to `_DRIVER_CASES` below — that's the whole
point of the interface.

The ONVIF mock here is deliberately a small, self-contained handler (not
shared with packages/sentinel_core/tests/test_onvif_driver.py's own mock)
so this cross-package suite has no import-path dependency on another
package's tests/ directory (which isn't installed or guaranteed to be on
sys.path) — this suite only needs discover()/health() to work, not the
full protocol surface the ONVIF-specific test file already covers in
detail. The four vendor-shim mocks (Hikvision/Dahua/Milestone/Genetec)
below follow the same self-contained rule.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

import httpx
import numpy as np
import pytest

from edge_agent.adapters.rtsp_driver import RtspSource
from sentinel_core.drivers.base import CameraSource, DiscoveryScope
from sentinel_core.drivers.dahua import DahuaSource
from sentinel_core.drivers.genetec import GenetecSource
from sentinel_core.drivers.hikvision import HikvisionSource
from sentinel_core.drivers.milestone import MilestoneSource
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


# --- Vendor shims: HTTP Digest auth (Hikvision, Dahua) ---------------------

_DIGEST_REALM = "Login to Conformance Cam"
_DIGEST_NONCE = "conformance-nonce"
_DIGEST_USERNAME = "admin"
_DIGEST_PASSWORD = "conformance-pass"


def _digest_challenge() -> httpx.Response:
    return httpx.Response(
        401,
        headers={
            "WWW-Authenticate": f'Digest realm="{_DIGEST_REALM}", nonce="{_DIGEST_NONCE}", '
            'qop="auth", algorithm=MD5'
        },
    )


def _digest_is_valid(request: httpx.Request) -> bool:
    """Recomputes RFC 7616 digest response server-side and compares -- this
    is what proves `httpx.DigestAuth`'s challenge/response round-trip is
    genuinely exercised, not just present as an unused client kwarg."""
    header = request.headers.get("authorization", "")
    if not header.startswith("Digest "):
        return False
    raw_pairs = re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]*))', header[len("Digest ") :])
    params = {k: (a or b) for k, a, b in raw_pairs}
    if params.get("username") != _DIGEST_USERNAME or params.get("nonce") != _DIGEST_NONCE:
        return False
    ha1 = hashlib.md5(f"{_DIGEST_USERNAME}:{_DIGEST_REALM}:{_DIGEST_PASSWORD}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{request.method}:{params.get('uri', '')}".encode()).hexdigest()
    nc = params.get("nc", "00000001")
    cnonce = params.get("cnonce", "")
    qop = params.get("qop", "auth")
    expected = hashlib.md5(f"{ha1}:{_DIGEST_NONCE}:{nc}:{cnonce}:{qop}:{ha2}".encode()).hexdigest()
    return params.get("response") == expected


def _mock_hikvision_handler(request: httpx.Request) -> httpx.Response:
    if not _digest_is_valid(request):
        return _digest_challenge()

    if request.url.path == "/ISAPI/System/deviceInfo":
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<DeviceInfo xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            "<deviceName>Conformance Gate Camera</deviceName>"
            "<model>DS-CONFORMANCE</model>"
            "<serialNumber>HIK-CONFORMANCE-001</serialNumber>"
            "</DeviceInfo>"
        )
    else:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<StreamingChannelList xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            "<StreamingChannel><id>101</id><channelName>Main</channelName></StreamingChannel>"
            "</StreamingChannelList>"
        )
    return httpx.Response(200, content=xml.encode(), headers={"Content-Type": "application/xml"})


def _make_hikvision_source() -> HikvisionSource:
    return HikvisionSource(
        username=_DIGEST_USERNAME,
        password=_DIGEST_PASSWORD,
        transport=httpx.MockTransport(_mock_hikvision_handler),
    )


def _mock_dahua_handler(request: httpx.Request) -> httpx.Response:
    if not _digest_is_valid(request):
        return _digest_challenge()

    if "getDeviceType" in request.url.query.decode():
        text = "type=IPC\r\n"
    else:
        text = "table.ChannelTitle[0].Name=Conformance Channel\r\n"
    return httpx.Response(200, content=text.encode(), headers={"Content-Type": "text/plain"})


def _make_dahua_source() -> DahuaSource:
    return DahuaSource(
        username=_DIGEST_USERNAME,
        password=_DIGEST_PASSWORD,
        transport=httpx.MockTransport(_mock_dahua_handler),
    )


# --- Vendor shims: token/session auth (Milestone, Genetec) -----------------

_BEARER_TOKEN = "conformance-bearer-token"


def _mock_milestone_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/IDP/connect/token":
        return httpx.Response(200, json={"access_token": _BEARER_TOKEN, "expires_in": 3600})
    if request.headers.get("authorization") != f"Bearer {_BEARER_TOKEN}":
        return httpx.Response(401, json={"error": "invalid_token"})
    return httpx.Response(
        200,
        json={
            "array": [
                {
                    "id": "conformance-cam-1",
                    "displayName": "Conformance Camera",
                    "streamUrl": "rtsp://127.0.0.1:8554/conformance/milestone1",
                    "enabled": True,
                }
            ]
        },
    )


def _make_milestone_source() -> MilestoneSource:
    return MilestoneSource(
        username="admin",
        password="conformance-pass",
        transport=httpx.MockTransport(_mock_milestone_handler),
    )


_SESSION_TOKEN = "conformance-session-token"


def _mock_genetec_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/WebSdk/Login":
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Basic "):
            return httpx.Response(401)
        decoded = base64.b64decode(auth[len("Basic ") :]).decode()
        if decoded != "admin:conformance-pass":
            return httpx.Response(401)
        return httpx.Response(200, json={"Session": _SESSION_TOKEN})
    if request.headers.get("session") != _SESSION_TOKEN:
        return httpx.Response(401)
    return httpx.Response(
        200,
        json={
            "Entities": [
                {
                    "Guid": "conformance-guid-1",
                    "Name": "Conformance Camera",
                    "StreamUri": "rtsp://127.0.0.1:8554/conformance/genetec1",
                    "Online": True,
                }
            ]
        },
    )


def _make_genetec_source() -> GenetecSource:
    return GenetecSource(
        username="admin",
        password="conformance-pass",
        transport=httpx.MockTransport(_mock_genetec_handler),
    )


@dataclass
class DriverCase:
    """One driver under test plus the scope that reaches its mock/fake."""

    name: str
    make_source: Callable[[], CameraSource]
    scope: DiscoveryScope


_DRIVER_CASES = [
    DriverCase("onvif", _make_onvif_source, DiscoveryScope(host="mock-cam")),
    DriverCase("rtsp", _make_rtsp_source, DiscoveryScope(host="rtsp://fake-camera/stream1")),
    DriverCase("hikvision", _make_hikvision_source, DiscoveryScope(host="mock-hik-cam")),
    DriverCase("dahua", _make_dahua_source, DiscoveryScope(host="mock-dahua-cam")),
    DriverCase("milestone", _make_milestone_source, DiscoveryScope(host="mock-milestone-server")),
    DriverCase("genetec", _make_genetec_source, DiscoveryScope(host="mock-genetec-server")),
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
