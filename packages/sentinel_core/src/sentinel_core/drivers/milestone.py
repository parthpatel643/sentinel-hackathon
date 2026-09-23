"""Milestone XProtect driver — a *contract-shaped mock* per
docs/01-ARCHITECTURE.md §4.1: real protocol shape (XProtect's IDP OAuth2
password-grant token endpoint, Bearer-authenticated REST/JSON), so a live
Management Server swap is a credential + base-URL change. No Milestone SDK
licence is used or implied.
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

__all__ = ["MilestoneSource"]


class MilestoneSource:
    """Directed-only: XProtect cameras are enumerated from one known
    Management Server base URL (`DiscoveryScope(host=...)`), not a network
    broadcast — this is how every real XProtect integration works too,
    since the Management Server is itself the directory of every camera in
    the recording group."""

    driver_id = "milestone"
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
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._username = username
        self._password = password
        self._timeout_s = timeout_s
        self._transport = transport

    async def _token(self, base: str, client: httpx.AsyncClient) -> str:
        """XProtect's IDP token endpoint — OAuth2 Resource Owner Password
        Credentials grant, exactly as the real `/IDP/connect/token`
        endpoint expects it (form-encoded, not JSON)."""
        resp = await client.post(
            f"{base}/IDP/connect/token",
            data={
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
                "client_id": "GrantValidatorClient",
            },
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        assert isinstance(token, str)
        return token

    async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
        if not scope.host:
            return []

        base = f"https://{scope.host}"
        async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as client:
            token = await self._token(base, client)
            resp = await client.get(
                f"{base}/api/rest/v1/cameras",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            cameras = resp.json()["array"]

        descriptors: list[CameraDescriptor] = []
        for cam in cameras:
            profiles = (
                [StreamProfile(protocol=StreamProtocol.RTSP, url=cam["streamUrl"])]
                if cam.get("streamUrl")
                else []
            )
            descriptors.append(
                CameraDescriptor(
                    camera_id=cam["id"],
                    name=cam.get("displayName", cam["id"]),
                    driver_id=self.driver_id,
                    profiles=profiles,
                    capabilities=self.capabilities,
                    status=CameraStatus.LIVE if cam.get("enabled") else CameraStatus.DOWN,
                    attributes={"milestone_host": scope.host, "milestone_camera_id": cam["id"]},
                )
            )
        return descriptors

    async def open(self, camera: CameraDescriptor, profile: StreamProfile) -> StreamHandle:
        return StreamHandle(url=profile.url, protocol=profile.protocol)

    async def health(self, camera: CameraDescriptor) -> SourceHealth:
        host = camera.attributes.get("milestone_host")
        if not host:
            return SourceHealth(status=CameraStatus.UNKNOWN, detail="No Management Server on file.")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                await self._token(f"https://{host}", client)
            return SourceHealth(status=CameraStatus.LIVE)
        except httpx.HTTPError as exc:
            return SourceHealth(status=CameraStatus.DOWN, detail=str(exc))
