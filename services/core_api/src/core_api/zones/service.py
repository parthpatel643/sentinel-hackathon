"""Zone rules service (M13) — configuring per-camera zones and recording
the violation events the edge worker's `ZoneRuleEngine`
(edge_agent.analytics.zone_rules) reports."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Zone, ZoneEvent
from core_api.zones.schemas import ZoneCreate, ZoneEventIn

__all__ = ["create_zone", "list_zone_events", "list_zones", "record_zone_event"]


async def create_zone(session: AsyncSession, camera_id: str, payload: ZoneCreate) -> Zone:
    zone = Zone(
        camera_id=camera_id,
        name=payload.name,
        rule_type=payload.rule_type,
        polygon=payload.polygon,
        dwell_threshold_s=payload.dwell_threshold_s,
        expected_direction_deg=payload.expected_direction_deg,
        direction_tolerance_deg=payload.direction_tolerance_deg,
        stopped_speed_threshold=payload.stopped_speed_threshold,
    )
    session.add(zone)
    await session.flush()
    return zone


async def list_zones(
    session: AsyncSession, camera_id: str, *, active_only: bool = True
) -> list[Zone]:
    query = select(Zone).where(Zone.camera_id == camera_id)
    if active_only:
        query = query.where(Zone.active.is_(True))
    result = await session.execute(query.order_by(Zone.created_at))
    return list(result.scalars().all())


async def record_zone_event(session: AsyncSession, payload: ZoneEventIn) -> ZoneEvent:
    event = ZoneEvent(
        zone_id=payload.zone_id,
        camera_id=payload.camera_id,
        rule_type=payload.rule_type,
        track_id=payload.track_id,
        dwell_time_s=payload.dwell_time_s,
        heading_deg=payload.heading_deg,
        observed_at=payload.observed_at,
    )
    session.add(event)
    await session.flush()
    return event


async def list_zone_events(
    session: AsyncSession, *, camera_id: str | None = None, limit: int = 200
) -> list[tuple[ZoneEvent, str]]:
    """Returns (event, zone_name) pairs — a plain join, not a nested
    relationship load, since this is a simple read-mostly listing query."""
    query = select(ZoneEvent, Zone.name).join(Zone, ZoneEvent.zone_id == Zone.id)
    if camera_id is not None:
        query = query.where(ZoneEvent.camera_id == camera_id)
    query = query.order_by(ZoneEvent.observed_at.desc()).limit(limit)
    result = await session.execute(query)
    return [(event, zone_name) for event, zone_name in result.all()]
