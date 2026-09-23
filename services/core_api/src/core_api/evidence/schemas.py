"""Evidence API wire schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EvidenceClipOut(BaseModel):
    id: UUID
    alert_id: UUID
    camera_id: str
    status: str = Field(description="pending | sealed | failed")
    sha256: str | None = None
    duration_s: float | None = None
    error: str | None = None
    created_at: datetime
    sealed_at: datetime | None = None

    model_config = {"from_attributes": True}


class RevealFaceRequest(BaseModel):
    reason: str = Field(
        min_length=5,
        description="Why this reveal is authorised — captured for audit, not just accepted.",
    )


class SignedMediaUrlOut(BaseModel):
    url: str = Field(
        description="A path + signed, time-limited query string — safe to embed directly "
        "in <img src>/<video src>, no Authorization header needed."
    )
