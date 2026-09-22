"""Admin Portal API wire schemas."""

from __future__ import annotations

from pydantic import BaseModel


class RetentionPreviewOut(BaseModel):
    detections_older_than_days: int
    clips_older_than_days: int
    detections_affected: int
    clips_affected: int
    clips_bytes_affected: int
