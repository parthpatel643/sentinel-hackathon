"""Watchlist + alerts HTTP API. See docs/01-ARCHITECTURE.md section 6.1-6.2
and docs/03-UX-DESIGN.md section 4.5 (Alerts) / 4.4 (the BOLO arm+retro-scan
call the "Find a Vehicle" screen's empty-result state offers)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.audit.service import record_audit_event
from core_api.auth.dependencies import current_user
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session, get_sessionmaker
from core_api.db.models import Alert
from core_api.evidence.schemas import EvidenceClipOut
from core_api.evidence.service import get_clip_for_alert, request_seal_clip, seal_clip_task
from core_api.watchlist.schemas import (
    AlertOut,
    AlertUpdate,
    BoloRequest,
    BoloResult,
    WatchlistEntryCreate,
    WatchlistEntryOut,
    WatchlistEntryUpdate,
)
from core_api.watchlist.service import (
    create_watchlist_entry,
    list_alerts,
    list_watchlist_entries,
    retro_scan,
    update_alert,
    update_watchlist_entry,
)
from sentinel_core.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["watchlist"])


@router.post("/watchlist", response_model=WatchlistEntryOut, status_code=201)
async def create_watchlist_entry_endpoint(
    payload: WatchlistEntryCreate,
    session: AsyncSession = Depends(get_session),
    user: TokenPayload = Depends(current_user),
) -> WatchlistEntryOut:
    entry = await create_watchlist_entry(session, payload)
    await record_audit_event(
        session,
        actor_email=user.email,
        action="watchlist_entry_created",
        resource_type="watchlist_entry",
        resource_id=str(entry.id),
        detail={"plate_normalised": entry.plate_normalised, "entry_type": entry.entry_type},
    )
    await session.commit()
    return WatchlistEntryOut.model_validate(entry)


@router.get("/watchlist", response_model=list[WatchlistEntryOut])
async def list_watchlist_endpoint(
    active_only: bool = Query(default=True), session: AsyncSession = Depends(get_session)
) -> list[WatchlistEntryOut]:
    entries = await list_watchlist_entries(session, active_only=active_only)
    return [WatchlistEntryOut.model_validate(e) for e in entries]


@router.patch("/watchlist/{entry_id}", response_model=WatchlistEntryOut)
async def update_watchlist_entry_endpoint(
    entry_id: UUID,
    payload: WatchlistEntryUpdate,
    session: AsyncSession = Depends(get_session),
    user: TokenPayload = Depends(current_user),
) -> WatchlistEntryOut:
    """Admin Portal list management (docs/03-UX-DESIGN.md §6) — deactivate
    an entry by hand rather than only ever waiting out valid_until."""
    entry = await update_watchlist_entry(session, entry_id, active=payload.active)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"no watchlist entry with id {entry_id}")
    await record_audit_event(
        session,
        actor_email=user.email,
        action="watchlist_entry_updated",
        resource_type="watchlist_entry",
        resource_id=str(entry_id),
        detail={"active": payload.active},
    )
    await session.commit()
    return WatchlistEntryOut.model_validate(entry)


@router.post("/bolo", response_model=BoloResult, status_code=201)
async def bolo_endpoint(
    payload: BoloRequest, session: AsyncSession = Depends(get_session)
) -> BoloResult:
    """One input, two directions in time: arm a forward-looking watchlist
    entry AND retro-scan every detection already on file for a match — the
    product's signature "BOLO moment" (00-SOLUTION-PLAN.md section 1.1)."""
    entry = await create_watchlist_entry(
        session,
        WatchlistEntryCreate(
            plate=payload.plate,
            entry_type=payload.entry_type,
            priority=payload.priority,
            case_reference=payload.case_reference,
            requested_by=payload.requested_by,
            notes=payload.notes,
        ),
    )
    alerts = await retro_scan(session, entry)
    await session.commit()

    return BoloResult(
        watchlist_entry=WatchlistEntryOut.model_validate(entry),
        retro_alerts_created=len(alerts),
        retro_sightings_found=sum(a.sighting_count for a in alerts),
    )


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts_endpoint(
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[AlertOut]:
    alerts = await list_alerts(session, status=status)
    return [AlertOut.model_validate(a) for a in alerts]


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
async def update_alert_endpoint(
    alert_id: UUID, payload: AlertUpdate, session: AsyncSession = Depends(get_session)
) -> AlertOut:
    alert = await update_alert(session, alert_id, payload)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    await session.commit()
    return AlertOut.model_validate(alert)


@router.post("/alerts/{alert_id}/seal-clip", response_model=EvidenceClipOut, status_code=202)
async def seal_clip_endpoint(
    alert_id: UUID,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> EvidenceClipOut:
    """Kicks off event-clip recording for this alert's camera and returns
    immediately with a 'pending' clip — sealing (recording, concatenating,
    hashing) happens in the background over the next ~evidence_post_roll_s
    seconds, per core_api/evidence/service.py. Poll GET .../clip until
    status is 'sealed' or 'failed'."""
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")

    clip = await request_seal_clip(session, alert)
    settings = get_settings()
    background_tasks.add_task(
        seal_clip_task, clip.id, alert.camera_id, settings, get_sessionmaker()
    )
    return EvidenceClipOut.model_validate(clip)


@router.get("/alerts/{alert_id}/clip", response_model=EvidenceClipOut)
async def get_alert_clip_endpoint(
    alert_id: UUID, session: AsyncSession = Depends(get_session)
) -> EvidenceClipOut:
    clip = await get_clip_for_alert(session, alert_id)
    if clip is None:
        raise HTTPException(
            status_code=404, detail="No clip has been requested for this alert yet."
        )
    return EvidenceClipOut.model_validate(clip)
