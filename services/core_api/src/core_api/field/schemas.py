"""Field PWA API wire schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PlateLookupMatch(BaseModel):
    entry_type: str
    priority: str
    match_rung: str
    case_reference: str | None


class PlateLookupOut(BaseModel):
    plate_normalised: str
    status: str
    matches: list[PlateLookupMatch]
    last_seen_at: datetime | None
    last_seen_camera_name: str | None


class FieldSightingOut(BaseModel):
    id: UUID
    client_report_id: str
    reported_by: str
    plate_text: str
    lat: float | None
    lon: float | None
    notes: str | None
    has_photo: bool
    created_at: datetime
