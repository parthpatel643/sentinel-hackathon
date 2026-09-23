"""Hikvision ISAPI driver — a *contract-shaped mock* per
docs/01-ARCHITECTURE.md §4.1: real protocol shape (HTTP Digest auth exactly
as ISAPI requires it, real ISAPI URL paths, real XML response shape), so a
live-camera swap is a credential change, not a rewrite. No Hikvision SDK
licence is used or implied.

ISAPI (Hikvision's "Intelligent Security API") is plain HTTP + XML, secured
with standard RFC 7616 HTTP Digest — unlike ONVIF's WS-Security, this rides
on the ordinary `WWW-Authenticate: Digest` challenge/response the `httpx`
client already implements via `httpx.DigestAuth`, so no hand-rolled crypto
is needed here (that's the whole point of picking a real, boring standard).
"""

from __future__ import annotations

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

__all__ = ["HikvisionSource"]

_ISAPI_NS = {"": "http://www.hikvision.com/ver20/XMLSchema"}


def _local_tag(tag: str) -> str:
    """Strip the ISAPI XML namespace so callers can address elements by
    their plain name (`DeviceInfo/deviceName`) without repeating the
    namespace URI everywhere — ISAPI uses a single default namespace, so
    this is safe and much more readable than qualified lookups."""
    return tag.rsplit("}", 1)[-1]


def _text_of(root: ET.Element, tag: str) -> str | None:
    for el in root.iter():
        if _local_tag(el.tag) == tag and el.text:
            return el.text
    return None


class HikvisionSource:
    """Directed-only (no vendor discovery protocol is used here — ISAPI has
    no standard broadcast probe; real deployments onboard Hikvision devices
    by IP, exactly like `DiscoveryScope(host=...)` already supports)."""

    driver_id = "hikvision"
    capabilities = SourceCapabilities(
        live=True,
        snapshot=True,
        playback=False,
        ptz=True,
        vendor_events=False,
        motion_metadata=False,
    )

    def __init__(
        self,
        *,
        username: str = "admin",
        password: str = "",
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._username = username
        self._password = password
        self._timeout_s = timeout_s
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout_s,
            transport=self._transport,
            auth=httpx.DigestAuth(self._username, self._password),
        )

    async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
        if not scope.host:
            # No multicast/broadcast discovery in ISAPI — directed probe only.
            return []

        base = f"http://{scope.host}"
        async with self._client() as client:
            info_resp = await client.get(f"{base}/ISAPI/System/deviceInfo")
            info_resp.raise_for_status()
            info = ET.fromstring(info_resp.content)

            channels_resp = await client.get(
                f"{base}/ISAPI/Streaming/channels", timeout=self._timeout_s
            )
            channels_resp.raise_for_status()
            channels_root = ET.fromstring(channels_resp.content)

        device_name = _text_of(info, "deviceName") or scope.host
        serial = _text_of(info, "serialNumber") or scope.host
        model = _text_of(info, "model")

        profiles_by_channel: dict[str, list[StreamProfile]] = {}
        for channel_el in channels_root:
            if _local_tag(channel_el.tag) != "StreamingChannel":
                continue
            channel_id = _text_of(channel_el, "id")
            if not channel_id:
                continue
            # ISAPI's own convention: rtsp://.../Streaming/Channels/<id>
            url = f"rtsp://{self._username}:{self._password}@{scope.host}:554/Streaming/Channels/{channel_id}"
            profiles_by_channel[channel_id] = [StreamProfile(protocol=StreamProtocol.RTSP, url=url)]

        return [
            CameraDescriptor(
                camera_id=f"{serial}-{channel_id}",
                name=f"{device_name} ({model})" if model else device_name,
                driver_id=self.driver_id,
                profiles=profiles,
                capabilities=self.capabilities,
                status=CameraStatus.UNKNOWN,
                attributes={"isapi_host": scope.host, "isapi_channel": channel_id},
            )
            for channel_id, profiles in profiles_by_channel.items()
        ]

    async def open(self, camera: CameraDescriptor, profile: StreamProfile) -> StreamHandle:
        return StreamHandle(url=profile.url, protocol=profile.protocol)

    async def health(self, camera: CameraDescriptor) -> SourceHealth:
        host = camera.attributes.get("isapi_host")
        if not host:
            return SourceHealth(status=CameraStatus.UNKNOWN, detail="No ISAPI host on file.")
        try:
            async with self._client() as client:
                resp = await client.get(f"http://{host}/ISAPI/System/deviceInfo")
            if resp.status_code == 200:
                return SourceHealth(status=CameraStatus.LIVE)
            return SourceHealth(
                status=CameraStatus.DOWN, detail=f"ISAPI returned HTTP {resp.status_code}"
            )
        except httpx.HTTPError as exc:
            return SourceHealth(status=CameraStatus.DOWN, detail=str(exc))
