"""Genetec Security Center driver — a *contract-shaped mock* per
docs/01-ARCHITECTURE.md §4.1: real protocol shape (Security Center's
Web SDK login endpoint issuing a session token consumed via a `Session`
header on every subsequent call, REST/JSON), so a live Security Center
swap is a credential + base-URL change. No Genetec SDK licence is used or
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

__all__ = ["GenetecSource"]


class GenetecSource:
    """Directed-only: Security Center entities are enumerated from one known
    Web SDK Gateway base URL (`DiscoveryScope(host=...)`) — like Milestone,
    the server itself is the directory."""

    driver_id = "genetec"
    capabilities = SourceCapabilities(
        live=True,
        snapshot=False,
        playback=True,
        ptz=True,
        vendor_events=True,
        motion_metadata=False,
    )

    def __init__(
        self,
        *,
        username: str = "admin",
        password: str = "",
        app_id: str = "sentinel-platform",
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._username = username
        self._password = password
        self._app_id = app_id
        self._timeout_s = timeout_s
        self._transport = transport

    async def _session(self, base: str, client: httpx.AsyncClient) -> str:
        """Security Center's Web SDK `Login` call — HTTP Basic on the way
        in, a bearer-style `Session` token back out, used as a header (not
        a cookie) on every subsequent request."""
        resp = await client.get(
            f"{base}/WebSdk/Login",
            params={"appId": self._app_id},
            auth=(self._username, self._password),
        )
        resp.raise_for_status()
        session = resp.json()["Session"]
        assert isinstance(session, str)
        return session

    async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
        if not scope.host:
            return []

        base = f"https://{scope.host}"
        async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as client:
            session = await self._session(base, client)
            resp = await client.get(
                f"{base}/WebSdk/Entities",
                params={"entityType": "Camera"},
                headers={"Session": session},
            )
            resp.raise_for_status()
            entities = resp.json()["Entities"]

        descriptors: list[CameraDescriptor] = []
        for entity in entities:
            stream_url = entity.get("StreamUri")
            descriptors.append(
                CameraDescriptor(
                    camera_id=entity["Guid"],
                    name=entity.get("Name", entity["Guid"]),
                    driver_id=self.driver_id,
                    profiles=(
                        [StreamProfile(protocol=StreamProtocol.RTSP, url=stream_url)]
                        if stream_url
                        else []
                    ),
                    capabilities=self.capabilities,
                    status=CameraStatus.LIVE if entity.get("Online") else CameraStatus.DOWN,
                    attributes={"genetec_host": scope.host, "genetec_guid": entity["Guid"]},
                )
            )
        return descriptors

    async def open(self, camera: CameraDescriptor, profile: StreamProfile) -> StreamHandle:
        return StreamHandle(url=profile.url, protocol=profile.protocol)

    async def health(self, camera: CameraDescriptor) -> SourceHealth:
        host = camera.attributes.get("genetec_host")
        if not host:
            return SourceHealth(status=CameraStatus.UNKNOWN, detail="No Security Center on file.")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                await self._session(f"https://{host}", client)
            return SourceHealth(status=CameraStatus.LIVE)
        except httpx.HTTPError as exc:
            return SourceHealth(status=CameraStatus.DOWN, detail=str(exc))
