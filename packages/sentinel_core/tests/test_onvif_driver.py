"""OnvifSource — driven against a mock ONVIF device, exercising the real
SOAP request/response shape and the real WS-Security digest computation
end to end, not just isinstance checks.

The mock is inlined here rather than imported from a shared fixtures
module: a second `tests/__init__.py` anywhere else in the tree (this
package already has none) risks exactly the top-level `tests` package-name
collision that a shared `packages/sentinel_core/tests/fixtures/` package
hit against `services/edge_agent/tests/` (which does have an __init__.py)
during a full `pytest` run — see tests/test_driver_conformance.py's own
docstring for the same reasoning.
"""

from __future__ import annotations

import base64
import hashlib
from xml.etree import ElementTree as ET

import httpx
import pytest

from sentinel_core.drivers.base import DiscoveryScope
from sentinel_core.drivers.onvif import OnvifSource
from sentinel_core.schemas.camera import CameraDescriptor, CameraStatus, StreamProtocol

MOCK_USERNAME = "admin"
MOCK_PASSWORD = "onvif-pass123"
MOCK_RTSP_URL = "rtsp://127.0.0.1:8554/mock/profile1"

_NS = {
    "soap": "http://www.w3.org/2003/05/soap-envelope",
    "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "wsu": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
}


def _soap_response(body_xml: str) -> httpx.Response:
    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
        'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
        'xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<soap:Body>{body_xml}</soap:Body></soap:Envelope>"
    )
    return httpx.Response(
        200, content=envelope.encode(), headers={"Content-Type": "application/soap+xml"}
    )


def _soap_fault(reason: str) -> httpx.Response:
    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body><soap:Fault>'
        f"<soap:Reason><soap:Text>{reason}</soap:Text></soap:Reason>"
        "</soap:Fault></soap:Body></soap:Envelope>"
    )
    return httpx.Response(
        400, content=envelope.encode(), headers={"Content-Type": "application/soap+xml"}
    )


def _verify_ws_security(root: ET.Element) -> bool:
    """Recomputes the WS-Security UsernameToken PasswordDigest the same way
    a real ONVIF device would, and rejects the request if it doesn't match
    — this is what makes the mock a genuine test of the driver's auth
    code, not just its XML shape."""
    token = root.find(".//wsse:UsernameToken", _NS)
    if token is None:
        return False
    username_el = token.find("wsse:Username", _NS)
    password_el = token.find("wsse:Password", _NS)
    nonce_el = token.find("wsse:Nonce", _NS)
    created_el = token.find("wsu:Created", _NS)
    if username_el is None or password_el is None or nonce_el is None or created_el is None:
        return False
    if username_el.text != MOCK_USERNAME:
        return False
    nonce = base64.b64decode(nonce_el.text or "")
    created = (created_el.text or "").encode()
    expected = base64.b64encode(
        hashlib.sha1(nonce + created + MOCK_PASSWORD.encode()).digest()
    ).decode()
    return password_el.text == expected


def _mock_onvif_handler(request: httpx.Request) -> httpx.Response:
    root = ET.fromstring(request.content)
    if not _verify_ws_security(root):
        return _soap_fault("Sender not Authorized")

    body = root.find(".//soap:Body", _NS)
    operation = body[0].tag.split("}")[-1] if body is not None and len(body) else ""

    if operation == "GetDeviceInformation":
        return _soap_response(
            "<tds:GetDeviceInformationResponse>"
            "<tds:Manufacturer>MockVendor</tds:Manufacturer>"
            "<tds:Model>MockCam-1000</tds:Model>"
            "<tds:FirmwareVersion>1.0.0</tds:FirmwareVersion>"
            "<tds:SerialNumber>MOCK-SERIAL-001</tds:SerialNumber>"
            "<tds:HardwareId>MOCK-HW-1</tds:HardwareId>"
            "</tds:GetDeviceInformationResponse>"
        )
    if operation == "GetProfiles":
        return _soap_response(
            '<trt:GetProfilesResponse><trt:Profiles token="Profile_1" fixed="true">'
            "<trt:Name>MainStream</trt:Name>"
            "</trt:Profiles></trt:GetProfilesResponse>"
        )
    if operation == "GetStreamUri":
        return _soap_response(
            f"<trt:GetStreamUriResponse><trt:MediaUri><trt:Uri>{MOCK_RTSP_URL}</trt:Uri>"
            "</trt:MediaUri></trt:GetStreamUriResponse>"
        )
    if operation in ("ContinuousMove", "Stop"):
        return _soap_response(f"<tptz:{operation}Response/>")

    return _soap_fault(f"Unsupported operation: {operation}")


def _source() -> OnvifSource:
    return OnvifSource(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        transport=httpx.MockTransport(_mock_onvif_handler),
    )


async def test_get_device_information_parses_the_real_response_shape() -> None:
    source = _source()

    info = await source.get_device_info("http://mock-cam/onvif/device_service")

    assert info["Manufacturer"] == "MockVendor"
    assert info["Model"] == "MockCam-1000"
    assert info["SerialNumber"] == "MOCK-SERIAL-001"


async def test_wrong_password_is_rejected_by_the_mock_device() -> None:
    """Proves the WS-Security digest is actually being checked, not just
    sent — a wrong password must fail the same way it would against a real
    ONVIF device."""
    source = OnvifSource(
        username=MOCK_USERNAME,
        password="wrong-password",
        transport=httpx.MockTransport(_mock_onvif_handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await source.get_device_info("http://mock-cam/onvif/device_service")


async def test_get_profiles_and_stream_uri() -> None:
    source = _source()

    profiles = await source.get_profiles("http://mock-cam/onvif/media_service")
    assert len(profiles) == 1
    assert profiles[0].token == "Profile_1"
    assert profiles[0].name == "MainStream"

    uri = await source.get_stream_uri("http://mock-cam/onvif/media_service", profiles[0].token)
    assert uri == MOCK_RTSP_URL


async def test_discover_with_a_directed_host_returns_one_camera_descriptor() -> None:
    source = _source()

    descriptors = await source.discover(DiscoveryScope(host="mock-cam"))

    assert len(descriptors) == 1
    descriptor = descriptors[0]
    assert descriptor.driver_id == "onvif"
    assert descriptor.camera_id == "MOCK-SERIAL-001"
    assert descriptor.name == "MockVendor MockCam-1000"
    assert len(descriptor.profiles) == 1
    assert descriptor.profiles[0].protocol is StreamProtocol.RTSP
    assert descriptor.profiles[0].url == MOCK_RTSP_URL
    assert descriptor.attributes["onvif_xaddr"] == "http://mock-cam/onvif/device_service"


async def test_health_reports_live_for_a_reachable_device() -> None:
    source = _source()
    descriptors = await source.discover(DiscoveryScope(host="mock-cam"))

    health = await source.health(descriptors[0])

    assert health.status is CameraStatus.LIVE


async def test_health_reports_unknown_without_a_recorded_device_address() -> None:
    source = _source()
    bare_descriptor = CameraDescriptor(camera_id="no-xaddr", name="Unknown", driver_id="onvif")

    health = await source.health(bare_descriptor)

    assert health.status is CameraStatus.UNKNOWN


async def test_ptz_continuous_move_and_stop_round_trip_without_error() -> None:
    """PTZ isn't asserted on every mock camera in the fleet, but a Profile-T
    device that declares ptz=True must at least be able to issue these two
    calls without the driver blowing up on the response shape."""
    source = _source()

    await source.ptz_continuous_move(
        "http://mock-cam/onvif/ptz_service", "Profile_1", pan=0.5, tilt=-0.5, zoom=0.0
    )
    await source.ptz_stop("http://mock-cam/onvif/ptz_service", "Profile_1")
