"""Admin Portal API wire schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RetentionPreviewOut(BaseModel):
    detections_older_than_days: int
    clips_older_than_days: int
    detections_affected: int
    clips_affected: int
    clips_bytes_affected: int


class RetentionExecuteRequest(BaseModel):
    detections_older_than_days: int = Field(default=30, ge=1)
    clips_older_than_days: int = Field(default=90, ge=1)


class RetentionExecutionOut(BaseModel):
    detections_older_than_days: int
    clips_older_than_days: int
    detections_deleted: int
    clips_deleted: int
    clips_bytes_deleted: int


class AuditLogEntryOut(BaseModel):
    id: UUID
    seq: int
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict[str, object]
    created_at: datetime
    prev_hash: str
    row_hash: str

    model_config = {"from_attributes": True}


class AuditChainVerificationOut(BaseModel):
    intact: bool
    rows_checked: int
    first_broken_seq: int | None = None
    detail: str | None = None


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
