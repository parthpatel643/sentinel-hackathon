"""Camera view alerts: API models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CameraEventIn", "CameraEventOut", "CameraEventUpdate", "CameraRestoredIn"]

CameraEventKind = Literal["view_shifted", "view_unrecognised"]


class CameraEventIn(BaseModel):
    """Posted by an edge worker when its view monitor confirms a change."""

    event_id: str = Field(pattern=r"^[0-9A-Za-z_-]{1,64}$")
    camera_id: str
    kind: CameraEventKind
    shift_pct: float | None = None
    rotation_deg: float | None = None
    scale: float | None = None
    match_ratio: float | None = None
    observed_at: datetime = Field(description="Processing time. Ordering only.")
    camera_time: datetime | None = Field(
        default=None, description="The camera's burned-in clock; null is time unknown"
    )
    has_snapshots: bool = False


class CameraRestoredIn(BaseModel):
    """Posted when the view lines up with the remembered one again."""

    camera_id: str
    observed_at: datetime
    camera_time: datetime | None = None


class CameraEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: str
    camera_id: str
    kind: str
    shift_pct: float | None
    rotation_deg: float | None
    scale: float | None
    match_ratio: float | None
    has_snapshots: bool
    observed_at: datetime = Field(description="Processing time. Ordering only; never display it.")
    camera_time: datetime | None = Field(
        description="The camera's burned-in clock when the change was confirmed; null is unknown"
    )
    status: str
    resolved_by: str | None
    restored_at: datetime | None
    created_at: datetime


class CameraEventUpdate(BaseModel):
    status: Literal["acknowledged", "resolved", "false_positive"]
    note: str | None = None
