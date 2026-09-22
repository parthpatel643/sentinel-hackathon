"""Detections HTTP API — ANPR event ingest (from edge workers) and search
(the Find-a-Vehicle screen's backend). See docs/01-ARCHITECTURE.md section
6.3 and docs/03-UX-DESIGN.md section 4.4."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.base import get_session
from core_api.detections.schemas import DetectionIn, DetectionOut, VehicleRoute
from core_api.detections.service import get_vehicle_route, ingest_detection, search_detections
from core_api.watchlist.schemas import AlertOut
from core_api.watchlist.service import correlate_detection

router = APIRouter(prefix="/api/v1", tags=["detections"])


@router.post("/detections", status_code=201, response_model=list[AlertOut])
async def ingest_detection_endpoint(
    payload: DetectionIn, session: AsyncSession = Depends(get_session)
) -> list[AlertOut]:
    """Posted by an edge worker for every resolved plate. Correlates against
    the active watchlist in the same request — a detection and whatever
    alert it triggers are decided together, never in two places that can
    drift out of sync."""
    detection = await ingest_detection(session, payload)
    alerts = await correlate_detection(session, detection)
    await session.commit()
    return [AlertOut.model_validate(a) for a in alerts]


@router.get("/detections", response_model=list[DetectionOut])
async def search_detections_endpoint(
    plate: str | None = Query(default=None),
    camera_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[DetectionOut]:
    return await search_detections(
        session, plate=plate, camera_id=camera_id, since=since, until=until, limit=limit
    )


@router.get("/vehicles/{plate}/route", response_model=VehicleRoute)
async def vehicle_route_endpoint(
    plate: str, session: AsyncSession = Depends(get_session)
) -> VehicleRoute:
    """The Find-a-Vehicle screen's single call: search + route reconstruction
    in one round trip."""
    return await get_vehicle_route(session, plate)
