"""Focused vendor-shim tests — beyond the shared conformance suite
(tests/test_driver_conformance.py), these exercise per-vendor wire-format
edge cases and auth-failure paths that are specific to each protocol shape,
not part of the common CameraSource contract.

Self-contained: no shared fixtures package (see the pytest package-name
collision documented in packages/sentinel_core/tests/test_onvif_driver.py's
git history) — each mock handler here is inlined."""

from __future__ import annotations

import base64
import hashlib
import re

import httpx
import pytest

from sentinel_core.drivers.base import DiscoveryScope
from sentinel_core.drivers.dahua import DahuaSource, _parse_kv
from sentinel_core.drivers.genetec import GenetecSource
from sentinel_core.drivers.hikvision import HikvisionSource
from sentinel_core.drivers.milestone import MilestoneSource
from sentinel_core.schemas.camera import CameraDescriptor, CameraStatus

_USERNAME = "admin"
_PASSWORD = "secret-pass"
_REALM = "Vendor Shim Test"
_NONCE = "shim-test-nonce"


def _digest_challenge() -> httpx.Response:
    challenge = f'Digest realm="{_REALM}", nonce="{_NONCE}", qop="auth", algorithm=MD5'
    return httpx.Response(401, headers={"WWW-Authenticate": challenge})


def _digest_is_valid(request: httpx.Request) -> bool:
    header = request.headers.get("authorization", "")
    if not header.startswith("Digest "):
        return False
    raw_pairs = re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]*))', header[len("Digest ") :])
    params = {k: (a or b) for k, a, b in raw_pairs}
    if params.get("username") != _USERNAME or params.get("nonce") != _NONCE:
        return False
    ha1 = hashlib.md5(f"{_USERNAME}:{_REALM}:{_PASSWORD}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{request.method}:{params.get('uri', '')}".encode()).hexdigest()
    nc = params.get("nc", "00000001")
    cnonce = params.get("cnonce", "")
    qop = params.get("qop", "auth")
    expected = hashlib.md5(f"{ha1}:{_NONCE}:{nc}:{cnonce}:{qop}:{ha2}".encode()).hexdigest()
    return params.get("response") == expected


# --- Hikvision ISAPI --------------------------------------------------------


def _hikvision_handler(request: httpx.Request) -> httpx.Response:
    if not _digest_is_valid(request):
        return _digest_challenge()
    if request.url.path == "/ISAPI/System/deviceInfo":
        xml = (
            '<DeviceInfo xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            "<deviceName>Gate Camera</deviceName>"
            "<model>DS-2CD2143G0</model>"
            "<serialNumber>HIK-SHIM-001</serialNumber>"
            "</DeviceInfo>"
        )
    else:
        xml = (
            '<StreamingChannelList xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            "<StreamingChannel><id>101</id><channelName>Main</channelName></StreamingChannel>"
            "<StreamingChannel><id>102</id><channelName>Sub</channelName></StreamingChannel>"
            "</StreamingChannelList>"
        )
    return httpx.Response(200, content=xml.encode())


async def test_hikvision_discover_returns_one_camera_per_channel() -> None:
    source = HikvisionSource(
        username=_USERNAME, password=_PASSWORD, transport=httpx.MockTransport(_hikvision_handler)
    )

    descriptors = await source.discover(DiscoveryScope(host="10.0.0.5"))

    assert len(descriptors) == 2
    assert descriptors[0].name == "Gate Camera (DS-2CD2143G0)"
    assert "Streaming/Channels/101" in descriptors[0].profiles[0].url


async def test_hikvision_discover_with_no_host_returns_empty() -> None:
    """ISAPI has no broadcast discovery protocol — a directed host is
    mandatory, and an undirected scope must degrade, not crash."""
    source = HikvisionSource(
        username=_USERNAME, password=_PASSWORD, transport=httpx.MockTransport(_hikvision_handler)
    )

    descriptors = await source.discover(DiscoveryScope(host=None))

    assert descriptors == []


async def test_hikvision_health_reports_down_on_wrong_credentials() -> None:
    source = HikvisionSource(
        username=_USERNAME, password="wrong", transport=httpx.MockTransport(_hikvision_handler)
    )
    descriptor = CameraDescriptor(
        camera_id="probe",
        name="probe",
        driver_id="hikvision",
        attributes={"isapi_host": "10.0.0.5"},
    )

    health = await source.health(descriptor)

    assert health.status is CameraStatus.DOWN


# --- Dahua CGI ---------------------------------------------------------------


def test_parse_kv_handles_dahua_table_array_syntax() -> None:
    parsed = _parse_kv("type=IPC\r\ntable.ChannelTitle[0].Name=Front Gate\r\n")

    assert parsed["type"] == "IPC"
    assert parsed["table.ChannelTitle[0].Name"] == "Front Gate"


def _dahua_handler(request: httpx.Request) -> httpx.Response:
    if not _digest_is_valid(request):
        return _digest_challenge()
    if "getDeviceType" in request.url.query.decode():
        text = "type=IPC\r\n"
    else:
        text = "table.ChannelTitle[0].Name=Front Gate\r\ntable.ChannelTitle[1].Name=Back Lot\r\n"
    return httpx.Response(200, content=text.encode())


async def test_dahua_discover_returns_one_camera_per_named_channel() -> None:
    source = DahuaSource(
        username=_USERNAME, password=_PASSWORD, transport=httpx.MockTransport(_dahua_handler)
    )

    descriptors = await source.discover(DiscoveryScope(host="10.0.0.6"))

    assert [d.name for d in descriptors] == ["Front Gate", "Back Lot"]
    assert "channel=1" in descriptors[0].profiles[0].url
    assert "channel=2" in descriptors[1].profiles[0].url


# --- Milestone XProtect (OAuth2 bearer) --------------------------------------


def _milestone_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/IDP/connect/token":
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        if form.get("password") != _PASSWORD:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"access_token": "shim-token", "expires_in": 3600})
    if request.headers.get("authorization") != "Bearer shim-token":
        return httpx.Response(401)
    return httpx.Response(
        200,
        json={
            "array": [
                {
                    "id": "cam-1",
                    "displayName": "Main Gate",
                    "streamUrl": "rtsp://x/1",
                    "enabled": True,
                },
                {"id": "cam-2", "displayName": "Disabled Cam", "streamUrl": None, "enabled": False},
            ]
        },
    )


async def test_milestone_discover_uses_bearer_token_from_idp() -> None:
    source = MilestoneSource(
        username=_USERNAME, password=_PASSWORD, transport=httpx.MockTransport(_milestone_handler)
    )

    descriptors = await source.discover(DiscoveryScope(host="vms.example.gov"))

    assert descriptors[0].status is CameraStatus.LIVE
    assert descriptors[1].status is CameraStatus.DOWN
    assert descriptors[1].profiles == []  # no streamUrl -> no profile, not a crash


async def test_milestone_token_request_rejects_wrong_password() -> None:
    source = MilestoneSource(
        username=_USERNAME, password="wrong", transport=httpx.MockTransport(_milestone_handler)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await source.discover(DiscoveryScope(host="vms.example.gov"))


# --- Genetec Security Center (session header) --------------------------------


def _genetec_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/WebSdk/Login":
        auth = request.headers.get("authorization", "")
        decoded = (
            base64.b64decode(auth[len("Basic ") :]).decode() if auth.startswith("Basic ") else ""
        )
        if decoded != f"{_USERNAME}:{_PASSWORD}":
            return httpx.Response(401)
        return httpx.Response(200, json={"Session": "shim-session"})
    if request.headers.get("session") != "shim-session":
        return httpx.Response(401)
    return httpx.Response(
        200,
        json={
            "Entities": [
                {"Guid": "guid-1", "Name": "Lobby", "StreamUri": "rtsp://x/lobby", "Online": True}
            ]
        },
    )


async def test_genetec_discover_uses_session_header_after_login() -> None:
    source = GenetecSource(
        username=_USERNAME, password=_PASSWORD, transport=httpx.MockTransport(_genetec_handler)
    )

    descriptors = await source.discover(DiscoveryScope(host="sc.example.gov"))

    assert len(descriptors) == 1
    assert descriptors[0].camera_id == "guid-1"
    assert descriptors[0].profiles[0].url == "rtsp://x/lobby"
