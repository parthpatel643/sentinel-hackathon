"""Camera registry domain model — the system of record for Model 1."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AnalyticsTier",
    "CameraDescriptor",
    "CameraStatus",
    "GeoPoint",
    "SourceCapabilities",
    "StreamProfile",
    "StreamProtocol",
]


class StreamProtocol(StrEnum):
    RTSP = "rtsp"
    HLS = "hls"
    WHEP = "whep"
    ONVIF = "onvif"


class CameraStatus(StrEnum):
    """Connection state machine for a camera."""

    UNKNOWN = "unknown"
    CONNECTING = "connecting"
    LIVE = "live"
    DEGRADED = "degraded"
    DOWN = "down"


class AnalyticsTier(StrEnum):
    """How much inference a camera earns. See 01-ARCHITECTURE section 4.3.

    Tiering is what makes 80,000 cameras tractable: a PDS godown camera and a
    highway check-post camera have nothing in common operationally.
    """

    A_CONTINUOUS = "a_continuous"
    B_SAMPLED = "b_sampled"
    C_MOTION_GATED = "c_motion_gated"
    D_REGISTRY_ONLY = "d_registry_only"

    @property
    def analytic_fps(self) -> float:
        return {
            AnalyticsTier.A_CONTINUOUS: 5.0,
            AnalyticsTier.B_SAMPLED: 1.0,
            AnalyticsTier.C_MOTION_GATED: 0.3,
            AnalyticsTier.D_REGISTRY_ONLY: 0.0,
        }[self]


class GeoPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class StreamProfile(BaseModel):
    """One way of consuming a camera. A camera usually exposes several."""

    model_config = ConfigDict(frozen=True)

    protocol: StreamProtocol
    url: str
    codec: str | None = Field(default=None, description="h264 / h265 — the grid is mixed")
    width: int | None = None
    height: int | None = None
    declared_fps: float | None = Field(
        default=None,
        description="Metadata only. Never used for timing — measure the real rate from PTS.",
    )


class SourceCapabilities(BaseModel):
    """What a federation driver can actually do for this camera.

    Surfaced in the UI so operators see why an action is unavailable instead of
    watching it fail.
    """

    model_config = ConfigDict(frozen=True)

    live: bool = True
    snapshot: bool = False
    playback: bool = False
    ptz: bool = False
    vendor_events: bool = False
    motion_metadata: bool = False


class CameraDescriptor(BaseModel):
    """A camera as discovered by a driver, before it is persisted to the registry."""

    camera_id: str
    name: str
    driver_id: str = Field(description="Which CameraSource implementation owns this camera")
    department: str | None = None
    site: str | None = None
    location: GeoPoint | None = None
    profiles: list[StreamProfile] = Field(default_factory=list)
    capabilities: SourceCapabilities = Field(default_factory=SourceCapabilities)
    tier: AnalyticsTier = AnalyticsTier.B_SAMPLED
    status: CameraStatus = CameraStatus.UNKNOWN
    last_seen_at: datetime | None = None
    attributes: dict[str, str] = Field(default_factory=dict)

    def profile_for(self, protocol: StreamProtocol) -> StreamProfile | None:
        return next((p for p in self.profiles if p.protocol is protocol), None)
