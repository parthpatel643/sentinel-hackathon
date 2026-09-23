"""Zone rules HTTP API (M13) — docs/05-DELIVERY-PLAN.md's "zone rules
(intrusion, loitering, wrong-way, stopped vehicle)." Configuration is
admin-gated; listing zones is genuinely dual-use (an operator viewing
config in the UI, or the edge worker fetching its camera's zones at
startup — same reasoning as `POST /cameras`), and the ingest endpoint is
service-token gated, matching detections' own machine-to-machine
pattern."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.auth.dependencies import (
    current_user,
    current_user_or_service,
    require_role,
    require_service_token,
)
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.zones.schemas import ZoneCreate, ZoneEventIn, ZoneEventOut, ZoneOut
from core_api.zones.service import create_zone, list_zone_events, list_zones, record_zone_event

router = APIRouter(prefix="/api/v1", tags=["zones"])


@router.post("/cameras/{camera_id}/zones", response_model=ZoneOut, status_code=201)
async def create_zone_endpoint(
    camera_id: str,
    payload: ZoneCreate,
    session: AsyncSession = Depends(get_session),
    _admin: TokenPayload = Depends(require_role("admin")),
) -> ZoneOut:
    zone = await create_zone(session, camera_id, payload)
    await session.commit()
    return ZoneOut.model_validate(zone)


@router.get("/cameras/{camera_id}/zones", response_model=list[ZoneOut])
async def list_zones_endpoint(
    camera_id: str,
    active_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    _caller: TokenPayload | None = Depends(current_user_or_service),
) -> list[ZoneOut]:
    zones = await list_zones(session, camera_id, active_only=active_only)
    return [ZoneOut.model_validate(z) for z in zones]


@router.post("/zone-events", status_code=201)
async def record_zone_event_endpoint(
    payload: ZoneEventIn,
    session: AsyncSession = Depends(get_session),
    _svc: None = Depends(require_service_token),
) -> None:
    """Posted by the edge worker's `ZoneRuleEngine` (services/edge_agent's
    analytics/zone_rules.py) whenever a configured rule fires."""
    await record_zone_event(session, payload)
    await session.commit()


@router.get("/zone-events", response_model=list[ZoneEventOut])
async def list_zone_events_endpoint(
    camera_id: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> list[ZoneEventOut]:
    pairs = await list_zone_events(session, camera_id=camera_id, limit=limit)
    return [
        ZoneEventOut(
            id=event.id,
            zone_id=event.zone_id,
            zone_name=zone_name,
            camera_id=event.camera_id,
            rule_type=event.rule_type,
            track_id=event.track_id,
            dwell_time_s=event.dwell_time_s,
            heading_deg=event.heading_deg,
            observed_at=event.observed_at,
        )
        for event, zone_name in pairs
    ]
