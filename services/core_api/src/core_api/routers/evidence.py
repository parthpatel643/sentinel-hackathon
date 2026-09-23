"""Evidence media serving — video streaming for sealed clips. Split out from
routers/watchlist.py specifically because this route needs a different auth
model than the rest of that router (which blanket-applies `Depends(
current_user)` at `include_router()` time in app.py): this one also accepts
a signed, time-limited URL (M12 — see core_api/security/signed_urls.py),
so it can be embedded directly in a `<video src>` without an Authorization
header. Clip metadata (status, sha256, ...) stays a normal JWT-gated route
on watchlist_router; only the actual video bytes move here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.auth.dependencies import current_user, current_user_or_signed_url
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.db.models import EvidenceClip
from core_api.evidence.schemas import SignedMediaUrlOut
from core_api.security.signed_urls import sign_media_path
from sentinel_core.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["evidence"])


@router.get("/evidence/clips/{clip_id}/video")
async def stream_clip_video_endpoint(
    clip_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload | None = Depends(current_user_or_signed_url),
) -> FileResponse:
    clip = await session.get(EvidenceClip, clip_id)
    if clip is None or clip.status != "sealed" or not clip.file_path:
        raise HTTPException(status_code=404, detail="This clip is not sealed yet.")
    path = Path(clip.file_path)
    if not await asyncio.to_thread(path.is_file):
        raise HTTPException(status_code=404, detail="Sealed clip file is missing on disk.")
    return FileResponse(path, media_type="video/mp4", filename=f"{clip_id}.mp4")


@router.get("/evidence/clips/{clip_id}/video-url", response_model=SignedMediaUrlOut)
async def clip_video_signed_url_endpoint(
    clip_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> SignedMediaUrlOut:
    """Mints a signed, time-limited URL for the video above — requires a
    real login to mint, but the minted URL works unauthenticated for its
    short lifetime, exactly so it can be dropped straight into a
    `<video src>`."""
    clip = await session.get(EvidenceClip, clip_id)
    if clip is None or clip.status != "sealed" or not clip.file_path:
        raise HTTPException(status_code=404, detail="This clip is not sealed yet.")
    settings = get_settings()
    path = f"/api/v1/evidence/clips/{clip_id}/video"
    query = sign_media_path(path, settings=settings)
    return SignedMediaUrlOut(url=f"{path}?{query}")
