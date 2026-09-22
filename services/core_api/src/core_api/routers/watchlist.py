"""Watchlist + alerts HTTP API. See docs/01-ARCHITECTURE.md section 6.1-6.2
and docs/03-UX-DESIGN.md section 4.5 (Alerts) / 4.4 (the BOLO arm+retro-scan
call the "Find a Vehicle" screen's empty-result state offers)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.base import get_session
from core_api.watchlist.schemas import (
    AlertOut,
    AlertUpdate,
    BoloRequest,
    BoloResult,
    WatchlistEntryCreate,
    WatchlistEntryOut,
)
from core_api.watchlist.service import (
    create_watchlist_entry,
    list_alerts,
    list_watchlist_entries,
    retro_scan,
    update_alert,
)

router = APIRouter(prefix="/api/v1", tags=["watchlist"])


@router.post("/watchlist", response_model=WatchlistEntryOut, status_code=201)
async def create_watchlist_entry_endpoint(
    payload: WatchlistEntryCreate, session: AsyncSession = Depends(get_session)
) -> WatchlistEntryOut:
    entry = await create_watchlist_entry(session, payload)
    await session.commit()
    return WatchlistEntryOut.model_validate(entry)


@router.get("/watchlist", response_model=list[WatchlistEntryOut])
async def list_watchlist_endpoint(
    active_only: bool = Query(default=True), session: AsyncSession = Depends(get_session)
) -> list[WatchlistEntryOut]:
    entries = await list_watchlist_entries(session, active_only=active_only)
    return [WatchlistEntryOut.model_validate(e) for e in entries]


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
