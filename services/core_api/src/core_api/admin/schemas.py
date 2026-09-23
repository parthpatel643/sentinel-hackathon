"""Admin Portal API wire schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RetentionPreviewOut(BaseModel):
    detections_older_than_days: int
    clips_older_than_days: int
    detections_affected: int
    clips_affected: int
    clips_bytes_affected: int


class IntegrationStatusOut(BaseModel):
    provider_id: str
    name: str
    description: str
    mode: str = "mock"
    connected: bool
    detail: str
    sample_operation: str
    sample_latency_ms: float | None = None
    checked_at: datetime
