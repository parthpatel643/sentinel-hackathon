"""Detections HTTP API — ANPR event ingest (from edge workers) and search
(the Find-a-Vehicle screen's backend). See docs/01-ARCHITECTURE.md section
6.3 and docs/03-UX-DESIGN.md section 4.4."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.auth.dependencies import current_user, require_role, require_service_token
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.detections.schemas import DetectionIn, DetectionOut, VehicleRoute
from core_api.detections.service import get_vehicle_route, ingest_detection, search_detections
from core_api.evidence.reveal import (
    record_reveal_audit,
    resolve_original_path,
    resolve_snapshot_path,
)
from core_api.evidence.schemas import RevealFaceRequest
from core_api.reports.service import build_movement_report_zip
from core_api.security.mtls import edge_gateway_identity
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
    for audit, on top of (not instead of) the service-token check above."""
    detection = await ingest_detection(session, payload)
    alerts = await correlate_detection(session, detection)
    await session.commit()
    if edge_identity:
        logger.info(
            "detection_ingested_via_mtls_gateway",
            extra={"edge_identity": edge_identity, "camera_id": payload.camera_id},
        )
    return [AlertOut.model_validate(a) for a in alerts]


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


@router.get("/vehicles/{plate}/route", response_model=VehicleRoute)
async def vehicle_route_endpoint(
    plate: str,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> VehicleRoute:
    """The Find-a-Vehicle screen's single call: search + route reconstruction
    in one round trip."""
    return await get_vehicle_route(session, plate)


@router.get("/vehicles/{plate}/movement-report")
async def movement_report_endpoint(
    plate: str,
    session: AsyncSession = Depends(get_session),
    user: TokenPayload = Depends(current_user),
) -> Response:
    """The Movement Report export — a zip of report.pdf, report.csv and a
    hash manifest binding them together (docs/01-ARCHITECTURE.md §6.3/§6.5).
    'This is literally the eval-day deliverable.'"""
    route = await get_vehicle_route(session, plate)
    zip_bytes, filename = build_movement_report_zip(route, generated_by=user.email)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/detections/{event_id}/snapshot")
async def detection_snapshot_endpoint(
    event_id: str,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> FileResponse:
    """The default, face-blurred-by-default snapshot (M12) — safe for any
    authenticated user, no reveal workflow needed. See
    core_api/evidence/reveal.py."""
    path = await resolve_snapshot_path(session, event_id, get_settings())
    if path is None:
        raise HTTPException(status_code=404, detail="No snapshot on file for this detection.")
    return FileResponse(path, media_type="image/jpeg", filename=f"{event_id}.jpg")


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
