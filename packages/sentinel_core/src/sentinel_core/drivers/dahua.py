"""Dahua CGI driver — a *contract-shaped mock* per docs/01-ARCHITECTURE.md
§4.1: real protocol shape (HTTP Digest auth, real `/cgi-bin/*.cgi` paths,
real `key=value` plaintext response parsing — Dahua's classic API returns
neither JSON nor XML but bare `key.subkey=value\r\n` lines), so a live
device swap is a credential change. No Dahua SDK licence is used or
implied.
"""

from __future__ import annotations

import httpx

from sentinel_core.drivers.base import DiscoveryScope, SourceHealth, StreamHandle
from sentinel_core.schemas.camera import (
    CameraDescriptor,
    CameraStatus,
    SourceCapabilities,
    StreamProfile,
    StreamProtocol,
)

__all__ = ["DahuaSource"]


def _parse_kv(text: str) -> dict[str, str]:
    """Dahua's CGI responses are lines of `key=value` (sometimes
    `table.field[0]=value` for arrays) — not JSON/XML. This is deliberately
    a flat parser, not a full array/table unflattener, since the two calls
    this driver makes only need scalar keys."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


class DahuaSource:
    """Directed-only, like Hikvision — Dahua's CGI API has no vendor
    discovery broadcast either; `DiscoveryScope(host=...)` is required."""

    driver_id = "dahua"
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
            return []

        base = f"http://{scope.host}"
        async with self._client() as client:
            type_resp = await client.get(f"{base}/cgi-bin/magicBox.cgi?action=getDeviceType")
            type_resp.raise_for_status()
            device = _parse_kv(type_resp.text)

            channels_resp = await client.get(
                f"{base}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"
            )
            channels_resp.raise_for_status()
            channels = _parse_kv(channels_resp.text)

        device_type = device.get("type", "IPC")
        # e.g. "table.ChannelTitle[0].Name=Front Gate" -> channel index 0
        channel_names: dict[str, str] = {}
        for key, value in channels.items():
            if key.startswith("table.ChannelTitle[") and key.endswith("].Name"):
                index = key[len("table.ChannelTitle[") : -len("].Name")]
                channel_names[index] = value
        if not channel_names:
            channel_names = {"0": device_type}

        descriptors: list[CameraDescriptor] = []
        for index, name in channel_names.items():
            channel = int(index) + 1  # Dahua's realmonitor channel param is 1-based
            url = (
                f"rtsp://{self._username}:{self._password}@{scope.host}:554"
                f"/cam/realmonitor?channel={channel}&subtype=0"
            )
            descriptors.append(
                CameraDescriptor(
                    camera_id=f"{scope.host}-ch{channel}",
                    name=name or f"{device_type} channel {channel}",
                    driver_id=self.driver_id,
                    profiles=[StreamProfile(protocol=StreamProtocol.RTSP, url=url)],
                    capabilities=self.capabilities,
                    status=CameraStatus.UNKNOWN,
                    attributes={"dahua_host": scope.host, "dahua_channel": str(channel)},
                )
            )
        return descriptors

    async def open(self, camera: CameraDescriptor, profile: StreamProfile) -> StreamHandle:
        return StreamHandle(url=profile.url, protocol=profile.protocol)

    async def health(self, camera: CameraDescriptor) -> SourceHealth:
        host = camera.attributes.get("dahua_host")
        if not host:
            return SourceHealth(status=CameraStatus.UNKNOWN, detail="No Dahua host on file.")
        try:
            async with self._client() as client:
                resp = await client.get(f"http://{host}/cgi-bin/magicBox.cgi?action=getDeviceType")
            if resp.status_code == 200:
                return SourceHealth(status=CameraStatus.LIVE)
            return SourceHealth(
                status=CameraStatus.DOWN, detail=f"CGI endpoint returned HTTP {resp.status_code}"
            )
        except httpx.HTTPError as exc:
            return SourceHealth(status=CameraStatus.DOWN, detail=str(exc))
