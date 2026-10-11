"""Watchlist + alerts API models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AlertOut",
    "AlertUpdate",
    "BoloRequest",
    "BoloResult",
    "WatchlistEntryCreate",
    "WatchlistEntryOut",
    "WatchlistEntryUpdate",
]


class WatchlistEntryCreate(BaseModel):
    plate: str = Field(description="Any format — normalised and ambiguity-keyed server-side")
    entry_type: str = Field(description="stolen | wanted | missing | suspect | bolo")
    priority: str = "medium"
    case_reference: str | None = None
    requested_by: str | None = None
    notes: str | None = None
    valid_until: datetime | None = None


class WatchlistEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plate_normalised: str
    entry_type: str
    priority: str
    case_reference: str | None
    requested_by: str | None
    notes: str | None
    active: bool
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime


class WatchlistEntryUpdate(BaseModel):
    active: bool


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    watchlist_entry_id: UUID
    camera_id: str
    detection_event_id: str
    plate_text: str
    match_rung: str
    match_confidence: float
    priority_score: float
    status: str
    sighting_count: int
    first_seen_at: datetime = Field(
        description="Processing time of the earliest sighting. Ordering only; never display it."
    )
    last_seen_at: datetime = Field(
        description="Processing time of the latest sighting. Ordering only; never display it."
    )
    first_seen_camera_time: datetime | None = Field(
        description="The camera's clock on the earliest sighting; null is time unknown"
    )
    last_seen_camera_time: datetime | None = Field(
        description="The camera's clock on the latest sighting; null is time unknown"
    )
    resolved_by: str | None
    resolution_note: str | None
    created_at: datetime


class AlertUpdate(BaseModel):
    status: str = Field(
        description="acknowledged | assigned | in_progress | resolved | false_positive"
    )
    resolved_by: str | None = None
    resolution_note: str | None = None


class BoloRequest(BaseModel):
    """Arm a watchlist entry AND immediately retro-scan history — the
    "BOLO moment" (00-SOLUTION-PLAN.md section 1.1): one input, two
    directions in time."""

    plate: str
    entry_type: str = "bolo"
    priority: str = "high"
    case_reference: str | None = None
    requested_by: str | None = None
    notes: str | None = None


class BoloResult(BaseModel):
    watchlist_entry: WatchlistEntryOut
    retro_alerts_created: int
    retro_sightings_found: int
    already_armed: bool = Field(
        default=False,
        description="True when an active entry already watched this plate for this reason: "
        "it is returned as-is and nothing is re-scanned, so no alert is duplicated.",
    )
