"""Detection ingest + search API models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from core_api.registry.schemas import GeoPointOut

__all__ = ["BoundingBoxIn", "DetectionIn", "DetectionOut", "RoutePoint", "VehicleRoute"]


class BoundingBoxIn(BaseModel):
    x: int
    y: int
    width: int
    height: int


class DetectionIn(BaseModel):
    """One ANPR read, posted by an edge worker. Mirrors
    `sentinel_core.schemas.Event` (type=anpr.plate_read) — the edge worker's
    AnprPipeline output maps onto this almost field-for-field."""

    event_id: str
    camera_id: str
    plate_text: str
    plate_normalised: str
    plate_ambiguity_key: str
    plate_confidence: float = Field(ge=0.0, le=1.0)
    format_valid: bool = False
    frames_voted: int = 1
    vehicle_class: str | None = None
    vehicle_colour: str | None = None
    vehicle_track_id: str | None = None
    bbox: BoundingBoxIn | None = None
    pts_ms: float
    observed_at: datetime
    snapshot_uri: str | None = None
    node_id: str
    model_versions: dict[str, str] = Field(default_factory=dict)


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    camera_id: str
    plate_text: str
    plate_normalised: str
    plate_confidence: float
    format_valid: bool
    frames_voted: int
    vehicle_class: str | None
    vehicle_colour: str | None
    vehicle_track_id: str | None
    observed_at: datetime
    snapshot_uri: str | None
    node_id: str


class RoutePoint(BaseModel):
    """One hop in a vehicle's reconstructed route — 03-UX-DESIGN.md section
    4.4's timeline + map. `confirmed` distinguishes an exact/ambiguity-class
    plate match from a (not yet implemented) appearance-based bridge — see
    docs/01-ARCHITECTURE.md section 6.3 for the full design."""

    event_id: str = Field(
        default="",
        description="Addresses GET /detections/{event_id}/snapshot. Without it a client "
        "holding a route has no way to fetch the frame behind a sighting: snapshot_uri is "
        "an internal `snapshot://<ulid>` reference, not a URL a browser can load.",
    )
    camera_id: str
    camera_name: str
    location: GeoPointOut | None
    observed_at: datetime
    plate_text: str
    plate_confidence: float
    match_rung: str = Field(description="exact | ambiguity_class")
    snapshot_uri: str | None
    confirmed: bool = True


class VehicleRoute(BaseModel):
    plate_normalised: str
    total_sightings: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    points: list[RoutePoint]
