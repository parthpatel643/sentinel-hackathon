"""A real ONVIF driver: WS-Discovery, GetDeviceInformation, media profiles,
GetStreamUri, and PTZ ContinuousMove/Stop — hand-rolled SOAP/XML rather than
a WSDL-based client library (no bundled WSDL files to keep in sync, and the
actual wire protocol stays fully visible in this one file instead of hidden
behind code generation).

WS-Security UsernameToken digest auth (the ONVIF-mandated auth mechanism)
is implemented for real: SHA-1(nonce + created + password), not stubbed.

Tested against a minimal mock ONVIF device server (an httpx.MockTransport
handler) inlined directly in test_onvif_driver.py and
test_driver_conformance.py — deliberately not a shared fixtures package,
to avoid a pytest package-name collision with services/edge_agent/tests.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import socket
import uuid
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

import httpx

from sentinel_core.drivers.base import DiscoveryScope, SourceHealth, StreamHandle
from sentinel_core.schemas.camera import (
    CameraDescriptor,
    CameraStatus,
    SourceCapabilities,
    StreamProfile,
    StreamProtocol,
)

__all__ = ["MediaProfile", "OnvifSource"]

_NS = {
    "soap": "http://www.w3.org/2003/05/soap-envelope",
    "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "wsu": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tptz": "http://www.onvif.org/ver20/ptz/wsdl",
    "sch": "http://www.onvif.org/ver10/schema",
    "d": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "a": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
}
for _prefix, _uri in _NS.items():
    ET.register_namespace(_prefix if _prefix != "soap" else "", _uri)

_WSD_MULTICAST_ADDR = ("239.255.255.250", 3702)


class MediaProfile:
    def __init__(self, token: str, name: str):
        self.token = token
        self.name = name


def _wsse_header(username: str, password: str) -> ET.Element:
    """Real WS-Security UsernameToken digest — not HTTP Basic auth, which
    ONVIF devices generally reject: PasswordDigest = Base64(SHA1(nonce +
    created + password)), with the raw nonce bytes sent Base64-encoded
    alongside it so the server can recompute and compare."""
    nonce = secrets.token_bytes(16)
    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(
        hashlib.sha1(nonce + created.encode() + password.encode()).digest()
    ).decode()

    security = ET.Element(f"{{{_NS['wsse']}}}Security")
    token = ET.SubElement(security, f"{{{_NS['wsse']}}}UsernameToken")
    ET.SubElement(token, f"{{{_NS['wsse']}}}Username").text = username
    pwd = ET.SubElement(
        token,
        f"{{{_NS['wsse']}}}Password",
        Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest",
    )
    pwd.text = digest
    ET.SubElement(token, f"{{{_NS['wsse']}}}Nonce").text = base64.b64encode(nonce).decode()
    ET.SubElement(token, f"{{{_NS['wsu']}}}Created").text = created
    return security


def _soap_envelope(body: ET.Element, *, username: str | None, password: str | None) -> bytes:
    envelope = ET.Element(f"{{{_NS['soap']}}}Envelope")
    header = ET.SubElement(envelope, f"{{{_NS['soap']}}}Header")
    if username and password:
        header.append(_wsse_header(username, password))
    soap_body = ET.SubElement(envelope, f"{{{_NS['soap']}}}Body")
    soap_body.append(body)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(envelope)


async def _soap_call(
    client: httpx.AsyncClient,
    url: str,
    body: ET.Element,
    *,
    username: str | None,
    password: str | None,
) -> ET.Element:
    payload = _soap_envelope(body, username=username, password=password)
    response = await client.post(
        url, content=payload, headers={"Content-Type": "application/soap+xml"}
    )
    response.raise_for_status()
    return ET.fromstring(response.content)


def _find(root: ET.Element, path: str) -> ET.Element | None:
    return root.find(path, _NS)


def _first_of(root: ET.Element, *paths: str) -> ET.Element | None:
    """`_find(root, a) or _find(root, b)` looks natural but `or` on an
    Element relies on its (deprecated, soon-to-change) truthiness — an
    element with no children is falsy today even when it was genuinely
    found. Explicit `is not None` checks instead."""
    for path in paths:
        found = _find(root, path)
        if found is not None:
            return found
    return None


def _findall(root: ET.Element, path: str) -> list[ET.Element]:
    return root.findall(path, _NS)


class OnvifSource:
    """docs/01-ARCHITECTURE.md's `onvif` driver. Covers WS-Discovery,
    GetDeviceInformation, GetProfiles/GetStreamUri and PTZ
    ContinuousMove/Stop — the operations that matter for onboarding a
    generic ONVIF Profile S camera into the registry and previewing it."""

    driver_id = "onvif"
    capabilities = SourceCapabilities(
        live=True,
        snapshot=False,
        playback=False,
        ptz=True,
        vendor_events=False,
        motion_metadata=False,
    )

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._username = username
        self._password = password
        self._timeout_s = timeout_s
        # Injectable so tests exercise the real SOAP request/response
        # parsing against an httpx.MockTransport instead of a live device —
        # see test_onvif_driver.py.
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport)

    # --- WS-Discovery ------------------------------------------------------

    def probe_multicast(self, timeout_s: float = 3.0) -> list[str]:
        """Real WS-Discovery: a UDP multicast Probe, collecting XAddrs from
        every ProbeMatch reply. Genuinely best-effort in production too —
        most CCTV networks are VLAN-segmented specifically to keep camera
        multicast traffic off the general LAN, which is exactly why
        directed discovery (DiscoveryScope.host) is the reliable path this
        driver also supports."""
        message_id = f"urn:uuid:{uuid.uuid4()}"
        probe = ET.Element(f"{{{_NS['soap']}}}Envelope")
        header = ET.SubElement(probe, f"{{{_NS['soap']}}}Header")
        ET.SubElement(header, f"{{{_NS['a']}}}MessageID").text = message_id
        ET.SubElement(
            header, f"{{{_NS['a']}}}To"
        ).text = "urn:schemas-xmlsoap-org:ws:2005:04:discovery"
        ET.SubElement(
            header, f"{{{_NS['a']}}}Action"
        ).text = "http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe"
        body = ET.SubElement(probe, f"{{{_NS['soap']}}}Body")
        probe_el = ET.SubElement(body, f"{{{_NS['d']}}}Probe")
        ET.SubElement(probe_el, f"{{{_NS['d']}}}Types").text = "dn:NetworkVideoTransmitter"
        payload = b'<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(probe)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout_s)
        xaddrs: list[str] = []
        try:
            sock.sendto(payload, _WSD_MULTICAST_ADDR)
            while True:
                try:
                    data, _addr = sock.recvfrom(65535)
                except TimeoutError:
                    break
                try:
                    reply = ET.fromstring(data)
                    for xaddrs_el in _findall(reply, ".//d:XAddrs"):
                        if xaddrs_el.text:
                            xaddrs.extend(xaddrs_el.text.split())
                except ET.ParseError:
                    continue
        except OSError:
            # Multicast genuinely unreachable — no route, network
            # unreachable, permission denied by a sandbox/VLAN. This is a
            # real, expected outcome (most CCTV networks are segmented
            # specifically to keep camera multicast off the general LAN),
            # not a bug: "found nothing" is the correct answer, not a crash.
            return []
        finally:
            sock.close()
        return xaddrs

    # --- Device / Media services --------------------------------------------

    async def get_device_info(self, xaddr: str) -> dict[str, str]:
        body = ET.Element(f"{{{_NS['tds']}}}GetDeviceInformation")
        async with self._client() as client:
            root = await _soap_call(
                client, xaddr, body, username=self._username, password=self._password
            )
        response = _find(root, ".//tds:GetDeviceInformationResponse")
        if response is None:
            return {}
        return {child.tag.split("}")[-1]: (child.text or "") for child in response}

    async def get_profiles(self, media_xaddr: str) -> list[MediaProfile]:
        body = ET.Element(f"{{{_NS['trt']}}}GetProfiles")
        async with self._client() as client:
            root = await _soap_call(
                client, media_xaddr, body, username=self._username, password=self._password
            )
        profiles = []
        for profile_el in _findall(root, ".//trt:Profiles"):
            token = profile_el.get("token", "")
            name_el = _first_of(profile_el, "trt:Name", "sch:Name")
            profiles.append(
                MediaProfile(
                    token=token, name=(name_el.text or token) if name_el is not None else token
                )
            )
        return profiles

    async def get_stream_uri(self, media_xaddr: str, profile_token: str) -> str:
        body = ET.Element(f"{{{_NS['trt']}}}GetStreamUri")
        stream_setup = ET.SubElement(body, f"{{{_NS['trt']}}}StreamSetup")
        ET.SubElement(stream_setup, f"{{{_NS['sch']}}}Stream").text = "RTP-Unicast"
        transport = ET.SubElement(stream_setup, f"{{{_NS['sch']}}}Transport")
        ET.SubElement(transport, f"{{{_NS['sch']}}}Protocol").text = "RTSP"
        ET.SubElement(body, f"{{{_NS['trt']}}}ProfileToken").text = profile_token

        async with self._client() as client:
            root = await _soap_call(
                client, media_xaddr, body, username=self._username, password=self._password
            )
        uri_el = _first_of(root, ".//trt:MediaUri/trt:Uri", ".//sch:Uri")
        if uri_el is None or not uri_el.text:
            raise ValueError(f"GetStreamUri returned no URI for profile {profile_token!r}")
        return uri_el.text

    # --- PTZ -----------------------------------------------------------------

    async def ptz_continuous_move(
        self, ptz_xaddr: str, profile_token: str, *, pan: float, tilt: float, zoom: float
    ) -> None:
        body = ET.Element(f"{{{_NS['tptz']}}}ContinuousMove")
        ET.SubElement(body, f"{{{_NS['tptz']}}}ProfileToken").text = profile_token
        velocity = ET.SubElement(body, f"{{{_NS['tptz']}}}Velocity")
        pan_tilt = ET.SubElement(velocity, f"{{{_NS['sch']}}}PanTilt")
        pan_tilt.set("x", str(pan))
        pan_tilt.set("y", str(tilt))
        zoom_el = ET.SubElement(velocity, f"{{{_NS['sch']}}}Zoom")
        zoom_el.set("x", str(zoom))
        async with self._client() as client:
            await _soap_call(
                client, ptz_xaddr, body, username=self._username, password=self._password
            )

    async def ptz_stop(self, ptz_xaddr: str, profile_token: str) -> None:
        body = ET.Element(f"{{{_NS['tptz']}}}Stop")
        ET.SubElement(body, f"{{{_NS['tptz']}}}ProfileToken").text = profile_token
        ET.SubElement(body, f"{{{_NS['tptz']}}}PanTilt").text = "true"
        ET.SubElement(body, f"{{{_NS['tptz']}}}Zoom").text = "true"
        async with self._client() as client:
            await _soap_call(
                client, ptz_xaddr, body, username=self._username, password=self._password
            )

    # --- CameraSource contract -------------------------------------------------

    async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
        """Directed discovery (scope.host set) hits one known device
        directly — the reliable path. Undirected discovery runs the real
        WS-Discovery multicast probe and then directs at every XAddr it
        finds."""
        xaddrs = (
            [f"http://{scope.host}/onvif/device_service"]
            if scope.host
            else self.probe_multicast(scope.timeout_s)
        )

        descriptors: list[CameraDescriptor] = []
        for xaddr in xaddrs:
            info = await self.get_device_info(xaddr)
            media_xaddr = xaddr.replace("device_service", "media_service")
            profiles = await self.get_profiles(media_xaddr)
            stream_profiles = []
            for profile in profiles:
                try:
                    uri = await self.get_stream_uri(media_xaddr, profile.token)
                    stream_profiles.append(StreamProfile(protocol=StreamProtocol.RTSP, url=uri))
                except (httpx.HTTPError, ValueError):
                    continue

            camera_id = info.get("SerialNumber") or xaddr
            name = " ".join(filter(None, [info.get("Manufacturer"), info.get("Model")])) or xaddr
            descriptors.append(
                CameraDescriptor(
                    camera_id=camera_id,
                    name=name,
                    driver_id=self.driver_id,
                    profiles=stream_profiles,
                    capabilities=self.capabilities,
                    status=CameraStatus.UNKNOWN,
                    attributes={"onvif_xaddr": xaddr, **{k: v for k, v in info.items() if v}},
                )
            )
        return descriptors

    async def open(self, camera: CameraDescriptor, profile: StreamProfile) -> StreamHandle:
        return StreamHandle(url=profile.url, protocol=profile.protocol)

    async def health(self, camera: CameraDescriptor) -> SourceHealth:
        xaddr = camera.attributes.get("onvif_xaddr")
        if not xaddr:
            return SourceHealth(
                status=CameraStatus.UNKNOWN, detail="No ONVIF device address on file."
            )
        try:
            info = await self.get_device_info(xaddr)
        except httpx.HTTPError as exc:
            return SourceHealth(status=CameraStatus.DOWN, detail=str(exc))
        if not info:
            return SourceHealth(
                status=CameraStatus.DEGRADED, detail="Device responded but sent no information."
            )
        return SourceHealth(status=CameraStatus.LIVE)
