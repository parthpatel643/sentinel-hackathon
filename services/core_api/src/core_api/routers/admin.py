"""Admin Portal HTTP API — docs/03-UX-DESIGN.md section 6."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.admin.schemas import (
    AuditChainVerificationOut,
    AuditLogEntryOut,
    IntegrationStatusOut,
    RetentionExecuteRequest,
    RetentionExecutionOut,
    RetentionPreviewOut,
)
from core_api.admin.service import (
    check_integration_statuses,
    execute_retention,
    list_audit_log,
    preview_retention,
)
from core_api.audit.service import verify_chain
from core_api.auth.dependencies import require_role
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/retention-preview", response_model=RetentionPreviewOut)
async def retention_preview_endpoint(
    detections_days: int = Query(default=30, ge=1, description="Delete detections older than this"),
    clips_days: int = Query(default=90, ge=1, description="Delete sealed clips older than this"),
    session: AsyncSession = Depends(get_session),
    _admin: TokenPayload = Depends(require_role("admin")),
) -> RetentionPreviewOut:
    """Real counts (and, for clips, real file sizes already on disk) behind
    the Admin Portal's retention sliders — this endpoint only ever reads;
    see /retention-execute for the real deletion."""
    result = await preview_retention(
        session, detections_older_than_days=detections_days, clips_older_than_days=clips_days
    )
    return RetentionPreviewOut(
        detections_older_than_days=detections_days,
        clips_older_than_days=clips_days,
        detections_affected=result.detections_affected,
        clips_affected=result.clips_affected,
        clips_bytes_affected=result.clips_bytes_affected,
    )


@router.post("/retention-execute", response_model=RetentionExecutionOut)
async def retention_execute_endpoint(
    payload: RetentionExecuteRequest,
    session: AsyncSession = Depends(get_session),
    admin: TokenPayload = Depends(require_role("admin")),
) -> RetentionExecutionOut:
    """The real deletion the preview sliders were always previewing (M12's
    "retention policy engine") — deletes sealed clips' files and rows, and
    detection rows, older than the given cutoffs, and records exactly what
    it did in the hash-chained audit log."""
    result = await execute_retention(
        session,
        detections_older_than_days=payload.detections_older_than_days,
        clips_older_than_days=payload.clips_older_than_days,
        actor_email=admin.email,
    )
    await session.commit()
    return RetentionExecutionOut(
        detections_older_than_days=payload.detections_older_than_days,
        clips_older_than_days=payload.clips_older_than_days,
        detections_deleted=result.detections_deleted,
        clips_deleted=result.clips_deleted,
        clips_bytes_deleted=result.clips_bytes_deleted,
    )


@router.get("/integrations", response_model=list[IntegrationStatusOut])
async def integrations_endpoint(
    _admin: TokenPayload = Depends(require_role("admin")),
) -> list[IntegrationStatusOut]:
    """Drives a real representative lookup against each ExternalRegistry
    provider (VAHAN/SARTHI/eGujCop/AFIS — docs/01-ARCHITECTURE.md §6.4) and
    reports whether it genuinely round-tripped, so the Admin Portal's
    Integrations tab can say "Connected (mock)" honestly."""
    return await check_integration_statuses()


@router.get("/audit-log", response_model=list[AuditLogEntryOut])
async def audit_log_endpoint(
    limit: int = Query(default=200, le=1000),
    session: AsyncSession = Depends(get_session),
    _admin: TokenPayload = Depends(require_role("admin")),
) -> list[AuditLogEntryOut]:
    """The Admin Portal's Audit log screen — newest first."""
    entries = await list_audit_log(session, limit=limit)
    return [AuditLogEntryOut.model_validate(e) for e in entries]


@router.post("/audit-log/verify", response_model=AuditChainVerificationOut)
async def verify_audit_log_endpoint(
    session: AsyncSession = Depends(get_session),
    _admin: TokenPayload = Depends(require_role("admin")),
) -> AuditChainVerificationOut:
    """The Admin Portal's "Verify integrity" button — walks the whole hash
    chain and reports whether it's intact (docs/01-ARCHITECTURE.md §7).
    Same logic as scripts/verify_audit_log.py, exposed over HTTP for the
    UI."""
    result = await verify_chain(session)
    return AuditChainVerificationOut(
        intact=result.intact,
        rows_checked=result.rows_checked,
        first_broken_seq=result.first_broken_seq,
        detail=result.detail,
    )
