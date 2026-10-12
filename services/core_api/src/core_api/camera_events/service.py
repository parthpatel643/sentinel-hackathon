"""Camera view alerts: recording, listing and triage.

One open alert per camera and kind: a camera that stays moved, or moves again
before anyone has looked, does not stack up duplicates. A view restored by the
edge closes its open alerts itself, recorded as such."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.camera_events.schemas import CameraEventIn, CameraRestoredIn
from core_api.db.models import CameraEvent

__all__ = [
    "OPEN_STATUSES",
    "RESTORED_BY",
    "list_camera_events",
    "record_camera_event",
    "record_view_restored",
    "update_camera_event",
]

OPEN_STATUSES = ("new", "acknowledged")
RESTORED_BY = "system: view restored"


async def record_camera_event(
    session: AsyncSession, payload: CameraEventIn
) -> tuple[CameraEvent, bool]:
    """`(event, created)`. The same edge event twice (a retried post), or a
    camera already alerted for this kind and not yet closed, returns the
    existing alert instead of a duplicate."""
    same = await session.scalar(select(CameraEvent).where(CameraEvent.event_id == payload.event_id))
    if same is not None:
        return same, False
    open_one = await session.scalar(
        select(CameraEvent)
        .where(
            CameraEvent.camera_id == payload.camera_id,
            CameraEvent.kind == payload.kind,
            CameraEvent.status.in_(OPEN_STATUSES),
        )
        .order_by(CameraEvent.observed_at.desc())
        .limit(1)
    )
    if open_one is not None:
        return open_one, False
    event = CameraEvent(
        event_id=payload.event_id,
        camera_id=payload.camera_id,
        kind=payload.kind,
        shift_pct=payload.shift_pct,
        rotation_deg=payload.rotation_deg,
        scale=payload.scale,
        match_ratio=payload.match_ratio,
        has_snapshots=payload.has_snapshots,
        observed_at=payload.observed_at,
        camera_time=payload.camera_time,
    )
    session.add(event)
    await session.flush()
    return event, True


async def record_view_restored(
    session: AsyncSession, payload: CameraRestoredIn
) -> list[CameraEvent]:
    """Close this camera's open view alerts: the edge saw the view line up
    with the remembered one again."""
    events = list(
        (
            await session.execute(
                select(CameraEvent).where(
                    CameraEvent.camera_id == payload.camera_id,
                    CameraEvent.status.in_(OPEN_STATUSES),
                )
            )
        )
        .scalars()
        .all()
    )
    for event in events:
        event.status = "resolved"
        event.resolved_by = RESTORED_BY
        event.restored_at = payload.camera_time or datetime.now(UTC)
    await session.flush()
    return events


async def list_camera_events(
    session: AsyncSession,
    *,
    status: str | None = None,
    camera_id: str | None = None,
    limit: int = 200,
) -> list[CameraEvent]:
    query = select(CameraEvent)
    if status:
        query = query.where(CameraEvent.status == status)
    if camera_id:
        query = query.where(CameraEvent.camera_id == camera_id)
    result = await session.execute(query.order_by(CameraEvent.observed_at.desc()).limit(limit))
    return list(result.scalars().all())


async def update_camera_event(
    session: AsyncSession, event_id: uuid.UUID, *, status: str, resolved_by: str
) -> CameraEvent | None:
    event = await session.get(CameraEvent, event_id)
    if event is None:
        return None
    event.status = status
    event.resolved_by = resolved_by
    await session.flush()
    return event
