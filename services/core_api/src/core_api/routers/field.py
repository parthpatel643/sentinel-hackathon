"""Field PWA HTTP API — docs/03-UX-DESIGN.md §5."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.auth.dependencies import current_user
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.field.schemas import FieldSightingOut, PlateLookupMatch, PlateLookupOut
from core_api.field.service import list_sightings, lookup_plate, record_sighting, sighting_to_out
from sentinel_core.config import get_settings

router = APIRouter(prefix="/api/v1/field", tags=["field"])


@router.get("/lookup/{plate}", response_model=PlateLookupOut)
async def lookup_plate_endpoint(
    plate: str,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> PlateLookupOut:
    """The Field PWA's "Look up" screen — one call answers clear/needs-
    attention and where the plate was last seen, so an officer on a weak
    connection isn't waiting on several round trips."""
    result = await lookup_plate(session, plate)
    return PlateLookupOut(
        plate_normalised=result.plate_normalised,
        status=result.status,
        matches=[PlateLookupMatch.model_validate(m) for m in result.matches],
        last_seen_at=result.last_seen_at,
        last_seen_camera_name=result.last_seen_camera_name,
    )


@router.post("/sightings", response_model=FieldSightingOut, status_code=201)
async def record_sighting_endpoint(
    client_report_id: str = Form(...),
    plate_text: str = Form(...),
    lat: float | None = Form(default=None),
    lon: float | None = Form(default=None),
    notes: str | None = Form(default=None),
    photo: UploadFile | None = None,
    session: AsyncSession = Depends(get_session),
    user: TokenPayload = Depends(current_user),
) -> Response:
    """Where the Field PWA's offline outbox lands once a queued report
    finally reaches the network — idempotent on client_report_id, so a
    retried submission after a dropped connection is never double-counted."""
    photo_bytes = await photo.read() if photo is not None else None
    settings = get_settings()
    reports_dir = Path(settings.field_reports_dir)

    report, created = await record_sighting(
        session,
        reports_dir=reports_dir,
        client_report_id=client_report_id,
        reported_by=user.email,
        plate_text=plate_text,
        lat=lat,
        lon=lon,
        notes=notes,
        photo_bytes=photo_bytes,
    )
    await session.commit()
    body = sighting_to_out(report)
    return Response(
        content=body.model_dump_json(),
        media_type="application/json",
        status_code=201 if created else 200,
    )


@router.get("/sightings", response_model=list[FieldSightingOut])
async def list_sightings_endpoint(
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> list[FieldSightingOut]:
    reports = await list_sightings(session)
    return [sighting_to_out(r) for r in reports]
