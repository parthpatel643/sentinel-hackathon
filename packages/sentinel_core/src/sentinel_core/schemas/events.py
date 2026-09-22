"""The event envelope — the platform's lingua franca.

Every analytic result, health change and stream anomaly travels as an Event.
Each one carries its PTS, its stream epoch, the model versions that produced it
and the node that emitted it: without that provenance an alert is an assertion,
not evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

from sentinel_core.schemas.camera import CameraStatus, GeoPoint

__all__ = [
    "AnprPayload",
    "BoundingBox",
    "Event",
    "EventType",
    "EvidenceRef",
    "HealthPayload",
    "PipelineProvenance",
    "VehicleAttributes",
    "new_event_id",
]

SCHEMA_VERSION: Literal["1.0"] = "1.0"


def new_event_id() -> str:
    """ULIDs: globally unique, lexicographically sortable by creation time."""
    return str(ULID())


class EventType(StrEnum):
    ANPR_PLATE_READ = "anpr.plate_read"
    VEHICLE_DETECTED = "vehicle.detected"
    STREAM_DISCONTINUITY = "stream.discontinuity"
    CAMERA_HEALTH = "camera.health"
    ZONE_VIOLATION = "zone.violation"
    CAMERA_TAMPER = "camera.tamper"


class BoundingBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: int
    y: int
    width: int
    height: int


class VehicleAttributes(BaseModel):
    """Appearance attributes, used for cross-camera re-identification when the
    plate is unreadable at a given camera."""

    model_config = ConfigDict(frozen=True)

    vehicle_class: str | None = None
    colour: str | None = None
    track_id: str | None = None


class AnprPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    plate_text: str
    plate_normalised: str = Field(
        description="Uppercased, whitespace/IND-prefix stripped. The key used for exact matching."
    )
    plate_ambiguity_key: str = Field(
        description="Ambiguous characters folded to a canonical class (0/O/D, 1/I/L, 2/Z, 5/S, "
        "8/B, 6/G, 4/A) so OCR confusions still collide on one index lookup."
    )
    plate_confidence: float = Field(ge=0.0, le=1.0)
    char_confidences: list[float] = Field(default_factory=list)
    format_valid: bool = Field(
        default=False,
        description="Matches Indian plate grammar and a real RTO state code",
    )
    frames_voted: int = Field(
        default=1,
        ge=1,
        description="How many frames of this track contributed to the temporal vote",
    )
    bbox: BoundingBox | None = None
    vehicle: VehicleAttributes | None = None


class HealthPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: CameraStatus
    measured_fps: float | None = Field(
        default=None, description="Derived from PTS, not from the declared frame rate"
    )
    declared_fps: float | None = None
    reconnects: int = 0
    discontinuities: int = 0
    first_idr_latency_ms: float | None = None
    detail: str | None = None


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_uri: str | None = None
    clip_uri: str | None = None
    sha256: str | None = Field(default=None, description="Chain-of-custody hash over the media")


class PipelineProvenance(BaseModel):
    """Which code and which model weights produced this event.

    Required for forensic defensibility, and it makes model upgrades measurable
    instead of anecdotal.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str
    models: dict[str, str] = Field(default_factory=dict)


EventPayload = Annotated[AnprPayload | HealthPayload, Field(union_mode="left_to_right")]


class Event(BaseModel):
    """The envelope. Immutable once emitted."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=new_event_id)
    type: EventType
    schema_version: Literal["1.0"] = SCHEMA_VERSION

    camera_id: str
    device_geo: GeoPoint | None = None

    pts_ms: float = Field(description="Authoritative stream time for this event")
    stream_epoch: datetime = Field(description="Absolute time of the current leg's PTS origin")
    observed_at: datetime = Field(
        description="stream_epoch + pts_ms. Never the arrival time of the frame."
    )
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    payload: EventPayload
    evidence: EvidenceRef = Field(default_factory=EvidenceRef)
    pipeline: PipelineProvenance

    @property
    def subject(self) -> str:
        """NATS/Kafka subject for this event."""
        return f"sentinel.events.{self.type.value}.{self.camera_id}"
