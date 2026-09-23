"""Zone rules API wire schemas (M13)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ZoneCreate(BaseModel):
    name: str
    rule_type: str = Field(description="intrusion | loitering | wrong_way | stopped_vehicle")
    polygon: list[list[float]] = Field(
        description="At least 3 [x, y] points, normalised [0, 1] frame coordinates"
    )
    dwell_threshold_s: float = 10.0
    expected_direction_deg: float = 0.0
    direction_tolerance_deg: float = 60.0
    stopped_speed_threshold: float = 0.01

    @field_validator("rule_type")
    @classmethod
    def _validate_rule_type(cls, v: str) -> str:
        allowed = {"intrusion", "loitering", "wrong_way", "stopped_vehicle"}
        if v not in allowed:
            raise ValueError(f"rule_type must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator("polygon")
    @classmethod
    def _validate_polygon(cls, v: list[list[float]]) -> list[list[float]]:
        if len(v) < 3:
            raise ValueError("polygon must have at least 3 points")
        for point in v:
            if len(point) != 2:
                raise ValueError("each polygon point must be an [x, y] pair")
        return v


class ZoneOut(BaseModel):
    id: UUID
    camera_id: str
    name: str
    rule_type: str
    polygon: list[list[float]]
    dwell_threshold_s: float
    expected_direction_deg: float
    direction_tolerance_deg: float
    stopped_speed_threshold: float
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ZoneEventIn(BaseModel):
    zone_id: UUID
    camera_id: str
    rule_type: str
    track_id: str
    dwell_time_s: float | None = None
    heading_deg: float | None = None
    observed_at: datetime


class ZoneEventOut(BaseModel):
    id: UUID
    zone_id: UUID
    zone_name: str | None = None
    camera_id: str
    rule_type: str
    track_id: str
    dwell_time_s: float | None
    heading_deg: float | None
    observed_at: datetime

    model_config = {"from_attributes": True}
