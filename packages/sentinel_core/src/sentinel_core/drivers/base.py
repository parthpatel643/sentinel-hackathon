"""Federation adapter framework — docs/01-ARCHITECTURE.md section 4.1's
`CameraSource` port. See drivers/onvif.py and drivers/rtsp.py for the two
concrete drivers that prove the interface is real, not just a diagram, and
tests/test_driver_conformance.py for the contract suite that runs the same
checks against both.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from sentinel_core.schemas.camera import (
    CameraDescriptor,
    CameraStatus,
    SourceCapabilities,
    StreamProfile,
    StreamProtocol,
)

__all__ = [
    "CameraSource",
    "DiscoveryScope",
    "SourceHealth",
    "StreamHandle",
    "VendorEvent",
]


class DiscoveryScope(BaseModel):
    """What to search. A directed probe (`host` set) is the reliable path in
    any real deployment — VLAN-segmented CCTV networks routinely block the
    UDP multicast WS-Discovery relies on, so production ONVIF onboarding
    tools always offer both. `host=None` triggers the multicast probe."""

    host: str | None = None
    timeout_s: float = 3.0


class StreamHandle(BaseModel):
    url: str
    protocol: StreamProtocol


class SourceHealth(BaseModel):
    status: CameraStatus
    detail: str | None = None


class VendorEvent(BaseModel):
    """A vendor-specific event pulled/pushed from a driver's event
    subscription (motion, tamper, line-crossing, ...) — normalised just
    enough to be logged/routed, not fully modelled per vendor."""

    event_type: str
    camera_id: str
    payload: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class CameraSource(Protocol):
    """One port, pluggable drivers — docs/01-ARCHITECTURE.md ADR: "Never
    modify a department's existing system... standards-first (ONVIF -> RTSP
    -> vendor SDK)." `capabilities` lets the UI show *why* an action is
    unavailable for a given camera instead of just failing silently."""

    driver_id: str
    capabilities: SourceCapabilities

    async def discover(self, scope: DiscoveryScope) -> list[CameraDescriptor]: ...

    async def open(self, camera: CameraDescriptor, profile: StreamProfile) -> StreamHandle: ...

    async def health(self, camera: CameraDescriptor) -> SourceHealth: ...
