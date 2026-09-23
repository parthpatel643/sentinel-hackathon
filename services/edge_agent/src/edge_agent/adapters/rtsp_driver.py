"""The `rtsp` driver — docs/01-ARCHITECTURE.md section 4.1's `CameraSource`
port, formalising the RTSP capture path (pipeline/capture.py) this project
has used since M1 as an explicit driver rather than a special case. RTSP
has no generic discovery protocol of its own (you already have the URL, or
you got it from ONVIF/a vendor SDK first) — `discover()` here means
"confirm this one known URL is a real, openable stream," not "find cameras
on the network."
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from edge_agent.pipeline.capture import (
    CaptureConfig,
    RtspCapture,
    VideoSource,
    _default_backend_factory,
)
from sentinel_core.drivers.base import DiscoveryScope, SourceHealth, StreamHandle
from sentinel_core.schemas.camera import (
    CameraDescriptor,
    CameraStatus,
    SourceCapabilities,
    StreamProfile,
    StreamProtocol,
)

__all__ = ["RtspSource"]


def _probe(url: str, backend_factory: Callable[[str], VideoSource]) -> tuple[bool, float | None]:
    """Blocking (cv2-backed, or a test double) — always run via
    asyncio.to_thread, never called directly from an async def."""
    capture = RtspCapture(
        CaptureConfig(camera_id="probe", url=url), backend_factory=backend_factory
    )
    if not capture.open():
        return False, None
    try:
        frame = capture.read()
        return frame is not None, capture.declared_fps
    finally:
        capture.close()


class RtspSource:
    driver_id = "rtsp"
    capabilities = SourceCapabilities(
        live=True,
        snapshot=False,
        playback=False,
        ptz=False,
        vendor_events=False,
        motion_metadata=False,
    )

    def __init__(self, *, backend_factory: Callable[[str], VideoSource] = _default_backend_factory):
        # Injectable so the driver conformance suite (tests/test_driver_
        # conformance.py) can exercise this against the same FakeVideoSource
        # double the capture-pipeline tests already use, instead of needing
        # a live RTSP camera in CI.
        self._backend_factory = backend_factory

    async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]:
        if not scope.host:
            return []
        url = scope.host  # the full rtsp:// URL, not a bare hostname
        opened, fps = await asyncio.to_thread(_probe, url, self._backend_factory)
        if not opened:
            return []
        return [
            CameraDescriptor(
                camera_id=url,
                name=url,
                driver_id=self.driver_id,
                profiles=[StreamProfile(protocol=StreamProtocol.RTSP, url=url, declared_fps=fps)],
                capabilities=self.capabilities,
                status=CameraStatus.LIVE,
            )
        ]

    async def open(self, camera: CameraDescriptor, profile: StreamProfile) -> StreamHandle:
        return StreamHandle(url=profile.url, protocol=profile.protocol)

    async def health(self, camera: CameraDescriptor) -> SourceHealth:
        profile = camera.profile_for(StreamProtocol.RTSP)
        if profile is None:
            return SourceHealth(status=CameraStatus.UNKNOWN, detail="No RTSP profile on file.")
        opened, _fps = await asyncio.to_thread(_probe, profile.url, self._backend_factory)
        if not opened:
            return SourceHealth(status=CameraStatus.DOWN, detail="Could not open the RTSP stream.")
        return SourceHealth(status=CameraStatus.LIVE)
