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
    observed_at: datetime = Field(
        description="When the edge processed the footage (stream_epoch + PTS). Internal "
        "ordering, deduplication and partitioning only — never reported as a sighting's time."
    )
    camera_time: datetime | None = Field(
        default=None,
        description="The clock the camera burned into the evidence frame, confirmed by another "
        "reading of it. The only time a sighting is reported with; null is time unknown.",
    )
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
    camera_time: datetime | None = Field(
        description="The clock the camera burned into the evidence frame. The only time to "
        "show for this sighting; null is time unknown (the camera's clock was unreadable)."
    )
    observed_at: datetime = Field(
        description="When the edge processed the footage. Ordering only; never display it."
    )
    ingested_at: datetime = Field(
        validation_alias="created_at",
        description=(
            "When this detection reached us. Use it to decide whether a read is *recent*; "
            "never display it as the sighting's time."
        ),
    )
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
    camera_time: datetime | None = Field(
        description="The clock the camera burned into this sighting's evidence frame — the "
        "time visible in its snapshot. Null in `VehicleRoute.untimed`: the clock was unreadable."
    )
    observed_at: datetime = Field(
        exclude=True,
        description="Processing time. Orders untimed sightings internally; never serialised.",
    )
    plate_text: str
    plate_confidence: float
    match_rung: str = Field(
        description="exact | ambiguity_class | edit_distance | partial_attribute"
    )
    snapshot_uri: str | None
    confirmed: bool = Field(
        default=True,
        description="False for an edit_distance hop: a different plate one character away, "
        "which an operator must confirm against the snapshot.",
    )
    implied_speed_kmh: float | None = Field(
        default=None,
        description="Speed a vehicle would need from the previous hop to this one",
    )
    infeasible: bool = Field(
        default=False,
        description="True when that speed is beyond any road vehicle: a cloned plate, a wrong "
        "camera clock, or a misattributed read",
    )


class VehicleRoute(BaseModel):
    plate_normalised: str
    total_sightings: int = Field(description="Timed and untimed sightings together")
    first_seen_at: datetime | None = Field(
        description="The camera's clock on the earliest timed sighting"
    )
    last_seen_at: datetime | None = Field(
        description="The camera's clock on the latest timed sighting"
    )
    points: list[RoutePoint] = Field(
        description="The route: sightings with a readable camera clock, in that clock's order"
    )
    untimed: list[RoutePoint] = Field(
        default_factory=list,
        description="Sightings whose camera clock could not be read. Real sightings, kept off "
        "the timed route because nothing else may stand in for the camera's time.",
    )
