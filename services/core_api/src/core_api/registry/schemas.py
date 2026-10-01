"""Registry API request/response models.

Distinct from `sentinel_core.schemas.CameraDescriptor` (the catalogue/wire
shape) — these are the HTTP contract, and include registry-only fields
(timestamps, resolved department/site names) that a catalogue entry does not
carry. `core_api/registry/service.py` converts between the two.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

__all__ = [
    "CameraCreate",
    "CameraHealthUpdate",
    "CameraOut",
    "CameraStreamOut",
    "CoverageGapReport",
    "DepartmentCreate",
    "DepartmentOut",
    "DeviceDiscoveryRequest",
    "DeviceDiscoveryResult",
    "DiscoveredCameraOut",
    "GapCell",
    "GeoPointOut",
    "StreamProfileIn",
    "StreamProfileOut",
]


class CameraStreamOut(BaseModel):
    """The one thing the Operator Console's live-preview needs: a URL a
    plain <video> tag can play with no credentials of its own. Never the
    camera's raw RTSP/WHEP profile URLs — those carry embedded credentials
    for gov-catalogue cameras and must never reach the browser."""

    available: bool
    hls_url: str | None = Field(
        default=None, description="Playable without credentials when available=true"
    )
    reason: str | None = Field(
        default=None, description="Plain-language explanation when available=false"
    )


class GeoPointOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    lat: float
    lon: float


class StreamProfileIn(BaseModel):
    protocol: str = Field(description="rtsp | hls | whep | onvif")
    url: str
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    declared_fps: float | None = None


class StreamProfileOut(StreamProfileIn):
    model_config = ConfigDict(from_attributes=True)


class DepartmentCreate(BaseModel):
    name: str
    code: str | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    code: str | None
    camera_count: int = 0


class CameraCreate(BaseModel):
    """Manual onboarding — the wizard's final POST (03-UX-DESIGN.md section
    4.6). `camera_id` is caller-supplied and must be unique; use a
    department/site name (not an id) so a non-technical operator never has
    to know a UUID."""

    camera_id: str
    name: str
    driver_id: str = "rtsp"
    department_name: str | None = None
    site_name: str | None = None
    location: GeoPointOut | None = None
    tier: str = "b_sampled"
    profiles: list[StreamProfileIn] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def _lifecycle_values_are_valid(cls, attributes: dict[str, str]) -> dict[str, str]:
        # Same rules as the bulk CSV import, so neither path can store a date
        # or consent the lifecycle report would silently ignore.
        from core_api.registry.lifecycle import validate_lifecycle_attribute

        for key, value in attributes.items():
            error = validate_lifecycle_attribute(key, value)
            if error is not None:
                raise ValueError(error)
        return attributes


class CameraOut(BaseModel):
    camera_id: str
    name: str
    display_name: str = Field(
        default="",
        description="Readable label derived from `name` for maps and lists. `name` is "
        "always the catalogue's own value, kept verbatim for provenance.",
    )
    locality: str = Field(
        default="",
        description="Place or administrative area lifted out of `name`, empty when the "
        "name carries none. Shown as a second line under `display_name`.",
    )
    driver_id: str
    department_name: str | None
    site_name: str | None
    location: GeoPointOut | None
    tier: str
    status: str = Field(
        description="unknown | connecting | live | degraded | down | stale — 'stale' when "
        "a worker reported on this camera but has not for camera_stale_after_s"
    )
    last_seen_at: datetime | None
    measured_fps: float | None = None
    declared_fps: float | None = None
    reconnects: int = 0
    discontinuities: int = 0
    tamper_status: str | None = None
    analysed_fps: float | None = Field(
        default=None, description="Frames per stream-second run through ANPR (tier-scheduled)"
    )
    analysis_lag_s: float | None = Field(
        default=None, description="How far behind live analysis was at the last heartbeat"
    )
    source: str
    attributes: dict[str, str]
    profiles: list[StreamProfileOut]
    created_at: datetime
    updated_at: datetime


class CameraHealthUpdate(BaseModel):
    """Posted by an edge worker's periodic heartbeat — the ops dashboard's
    Integrator Compliance panel (docs/01-ARCHITECTURE.md section 12) reads
    these same fields."""

    status: str = Field(description="connecting | live | degraded | down")
    analysed_fps: float | None = None
    stream_position_at: datetime | None = Field(
        default=None,
        description="Stream time of the latest frame the worker has read (connection epoch "
        "+ PTS). The API turns it into analysis lag against its own clock; the worker never "
        "reads a wall clock for timing.",
    )
    measured_fps: float | None = None
    declared_fps: float | None = None
    reconnects: int | None = None
    discontinuities: int | None = None
    tamper_status: str | None = Field(
        default=None, description="M13 — 'ok' | 'covered' | 'blurred' | 'moved'"
    )


class GapCell(BaseModel):
    """One cell of the coverage grid — see registry/gap_analysis.py."""

    model_config = ConfigDict(frozen=True)
    center: GeoPointOut
    covered: bool
    nearest_camera_id: str | None
    nearest_camera_distance_m: float | None


class CoverageGapReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_cells: int
    covered_cells: int
    uncovered_cells: int
    coverage_radius_m: float
    cell_size_m: float
    cells: list[GapCell]

    @property
    def coverage_ratio(self) -> float:
        return self.covered_cells / self.total_cells if self.total_cells else 0.0


class DeviceDiscoveryRequest(BaseModel):
    """Onboard every stream a single device exposes — an ONVIF camera, or a
    Hikvision/Dahua NVR's channels — from its management address and
    account, instead of typing one RTSP URL per channel."""

    driver: Literal["onvif", "hikvision", "dahua"]
    host: str = Field(description="Device management address, e.g. 10.20.1.15 or 10.20.1.15:8080")
    username: str | None = None
    password: SecretStr | None = None
    department_name: str | None = None
    site_name: str | None = None
    location: GeoPointOut | None = None
    dry_run: bool = Field(default=True, description="Preview only; nothing is written when true")


class DiscoveredCameraOut(BaseModel):
    camera_id: str
    name: str
    stream_count: int
    stream_urls: list[str] = Field(description="Credentials masked")


class DeviceDiscoveryResult(BaseModel):
    dry_run: bool
    discovered: list[DiscoveredCameraOut]
    onboarded: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    failed: list[dict[str, str]] = Field(default_factory=list)
