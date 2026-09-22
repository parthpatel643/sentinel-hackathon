"""Admin Portal HTTP API — docs/03-UX-DESIGN.md section 6."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.admin.schemas import RetentionPreviewOut
from core_api.admin.service import preview_retention
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
    the Admin Portal's retention sliders — no scheduled deletion job is
    wired up yet, so this only ever reads."""
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
