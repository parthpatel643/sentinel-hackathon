"""Detections HTTP API — ANPR event ingest (from edge workers) and search
(the Find-a-Vehicle screen's backend). See docs/01-ARCHITECTURE.md section
6.3 and docs/03-UX-DESIGN.md section 4.4."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.audit.service import record_audit_event
from core_api.auth.dependencies import (
    current_user,
    current_user_or_signed_url,
    require_role,
    require_service_token,
)
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.detections.schemas import DetectionIn, DetectionOut, VehicleRoute
from core_api.detections.service import (
    detection_exists,
    get_vehicle_route,
    ingest_detection,
    search_detections,
)
from core_api.events.broker import publish_models
from core_api.evidence.reveal import (
    record_reveal_audit,
    resolve_original_path,
    resolve_snapshot_path,
)
from core_api.evidence.schemas import RevealFaceRequest, SignedMediaUrlOut
from core_api.reports.service import build_movement_report_zip
from core_api.security.mtls import edge_gateway_identity
from core_api.security.signed_urls import sign_media_path
from core_api.watchlist.schemas import AlertOut
from core_api.watchlist.service import correlate_detection
from sentinel_core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["detections"])


@router.post("/detections", status_code=201, response_model=list[AlertOut])
async def ingest_detection_endpoint(
    payload: DetectionIn,
    session: AsyncSession = Depends(get_session),
    _svc: None = Depends(require_service_token),
    edge_identity: str | None = Depends(edge_gateway_identity),
) -> list[AlertOut]:
    """Posted by an edge worker for every resolved plate. Correlates against
    the active watchlist in the same request — a detection and whatever
    alert it triggers are decided together, never in two places that can
    drift out of sync. Gated by the shared service token, not a user
    login — see auth/dependencies.py. `edge_identity` is set only when the
    request genuinely passed through the mTLS edge-gateway (infra/compose/
    edge_gateway/) — an additional network-layer admission signal recorded
    for audit, on top of (not instead of) the service-token check above.

    Idempotent per event: an edge worker replays detections it could not
    deliver (edge_agent/outbox.py), and one whose first post timed out after
    it was stored must be accepted again, not fail and block the queue."""
    if await detection_exists(session, payload.event_id, payload.observed_at):
        return []
    detection = await ingest_detection(session, payload)
    alerts = await correlate_detection(session, detection)
    await session.commit()
    alert_models = [AlertOut.model_validate(a) for a in alerts]
    await publish_models(session, "alert", [(a.camera_id, a) for a in alert_models])
    if edge_identity:
        logger.info(
            "detection_ingested_via_mtls_gateway",
            extra={"edge_identity": edge_identity, "camera_id": payload.camera_id},
        )
    return alert_models


@router.get("/detections", response_model=list[DetectionOut])
async def search_detections_endpoint(
    plate: str | None = Query(default=None),
    camera_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> list[DetectionOut]:
    return await search_detections(
        session, plate=plate, camera_id=camera_id, since=since, until=until, limit=limit
    )


# A multi-day operation (the Phase-2 finale spans two days) needs to reach
# past yesterday; a week bounds the scan on a busy registry.
_WINDOW_HOURS = Query(default=24, ge=1, le=168, description="How far back to search")


@router.get("/vehicles/{plate}/route", response_model=VehicleRoute)
async def vehicle_route_endpoint(
    plate: str,
    window_hours: int = _WINDOW_HOURS,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> VehicleRoute:
    """The Find-a-Vehicle screen's single call: search + route reconstruction
    in one round trip."""
    return await get_vehicle_route(session, plate, window=timedelta(hours=window_hours))


@router.get("/vehicles/{plate}/movement-report")
async def movement_report_endpoint(
    plate: str,
    window_hours: int = _WINDOW_HOURS,
    session: AsyncSession = Depends(get_session),
    user: TokenPayload = Depends(current_user),
) -> Response:
    """The Movement Report export — a zip of report.pdf, report.csv and a
    hash manifest binding them together (docs/01-ARCHITECTURE.md §6.3/§6.5).
    'This is literally the eval-day deliverable.'"""
    route = await get_vehicle_route(session, plate, window=timedelta(hours=window_hours))
    settings = get_settings()
    snapshots = {
        point.event_id: path
        for point in route.points
        if (path := await resolve_snapshot_path(session, point.event_id, settings)) is not None
    }
    zip_bytes, filename = build_movement_report_zip(
        route, generated_by=user.email, snapshots=snapshots
    )
    await record_audit_event(
        session,
        actor_email=user.email,
        action="movement_report_exported",
        resource_type="vehicle",
        resource_id=route.plate_normalised,
        detail={"sightings": route.total_sightings, "file": filename},
    )
    await session.commit()
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_EVENT_ID = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
_JPEG_MAGIC = b"\xff\xd8\xff"


async def _read_jpeg(upload: UploadFile) -> bytes:
    data = await upload.read(_MAX_SNAPSHOT_BYTES + 1)
    if len(data) > _MAX_SNAPSHOT_BYTES:
        raise HTTPException(status_code=413, detail="snapshot larger than 8 MB")
    if not data.startswith(_JPEG_MAGIC):
        raise HTTPException(status_code=415, detail="snapshot is not a JPEG")
    return data


@router.put("/detections/{event_id}/snapshot", status_code=204)
async def upload_snapshot_endpoint(
    event_id: str,
    blurred: UploadFile,
    original: UploadFile | None = None,
    _svc: None = Depends(require_service_token),
) -> Response:
    """An edge worker on another machine hands over the evidence frames it
    wrote locally — the face-blurred one this API serves, and the original
    only the reveal workflow may read. A worker beside the API shares its
    snapshot directory and never calls this. The event id becomes a file
    name, so it is held to the ULID-ish alphabet the worker uses."""
    if not _EVENT_ID.fullmatch(event_id):
        raise HTTPException(status_code=422, detail="invalid event id")
    settings = get_settings()
    files = [(Path(settings.snapshots_dir), await _read_jpeg(blurred))]
    if original is not None:
        files.append((Path(settings.snapshot_originals_dir), await _read_jpeg(original)))

    def _write() -> None:
        for directory, data in files:
            directory.mkdir(parents=True, exist_ok=True)
            partial = directory / f".{event_id}.jpg.part"
            partial.write_bytes(data)
            partial.replace(directory / f"{event_id}.jpg")

    await asyncio.to_thread(_write)
    return Response(status_code=204)


@router.get("/detections/{event_id}/snapshot")
async def detection_snapshot_endpoint(
    event_id: str,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload | None = Depends(current_user_or_signed_url),
) -> FileResponse:
    """The default, face-blurred-by-default snapshot (M12) — safe for any
    authenticated user, no reveal workflow needed. Also accepts a signed,
    time-limited URL (see /snapshot-url below) so this can be embedded
    directly in an `<img src>`. See core_api/evidence/reveal.py."""
    path = await resolve_snapshot_path(session, event_id, get_settings())
    if path is None:
        raise HTTPException(status_code=404, detail="No snapshot on file for this detection.")
    return FileResponse(path, media_type="image/jpeg", filename=f"{event_id}.jpg")


@router.get("/detections/{event_id}/snapshot-url", response_model=SignedMediaUrlOut)
async def detection_snapshot_signed_url_endpoint(
    event_id: str,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> SignedMediaUrlOut:
    """Mints a signed, time-limited URL for the snapshot above — requires a
    real login to mint (this endpoint itself is not signature-accessible),
    but the minted URL works unauthenticated for its short lifetime,
    exactly so it can be dropped straight into an `<img src>`."""
    settings = get_settings()
    if await resolve_snapshot_path(session, event_id, settings) is None:
        raise HTTPException(status_code=404, detail="No snapshot on file for this detection.")
    path = f"/api/v1/detections/{event_id}/snapshot"
    query = sign_media_path(path, settings=settings)
    return SignedMediaUrlOut(url=f"{path}?{query}")


@router.post("/detections/{event_id}/reveal-face")
async def reveal_face_endpoint(
    event_id: str,
    payload: RevealFaceRequest,
    session: AsyncSession = Depends(get_session),
    admin: TokenPayload = Depends(require_role("admin")),
) -> Response:
    """Reveal-on-authorisation with reason capture (docs/05-DELIVERY-PLAN.md
    M12) — admin-only (no separate "supervisor" role exists yet, a
    documented scoping choice, not an oversight), and a reason is
    mandatory, not optional. Returns the unblurred original directly;
    every call is persisted to the hash-chained audit log with the actor,
    the reason and a timestamp (core_api/audit/service.py)."""
    path = await resolve_original_path(session, event_id, get_settings())
    if path is None:
        raise HTTPException(status_code=404, detail="No snapshot on file for this detection.")
    await record_reveal_audit(
        session, event_id=event_id, actor_email=admin.email, reason=payload.reason
    )
    await session.commit()
    return FileResponse(path, media_type="image/jpeg", filename=f"{event_id}-unblurred.jpg")
