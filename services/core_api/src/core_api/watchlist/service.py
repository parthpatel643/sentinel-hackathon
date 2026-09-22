"""Watchlist entries, the matching ladder, and alert lifecycle.

The matching ladder here implements rungs 1-2 of
docs/01-ARCHITECTURE.md section 6.1 (exact, then OCR-ambiguity-class).
Edit-distance and partial/wildcard (rungs 3-4) and appearance-based ReID
bridging (rung 6) are documented next steps, not silently dropped — see that
section for the full six-rung design.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Alert, Detection, WatchlistEntry
from core_api.watchlist.schemas import AlertUpdate, WatchlistEntryCreate
from sentinel_core.plates import ambiguity_key, normalise_plate

__all__ = [
    "ALERT_DEDUP_WINDOW",
    "PRIORITY_WEIGHT",
    "correlate_detection",
    "create_watchlist_entry",
    "list_alerts",
    "list_watchlist_entries",
    "retro_scan",
    "update_alert",
]

PRIORITY_WEIGHT = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
RUNG_WEIGHT = {"exact": 1.0, "ambiguity_class": 0.7}
TERMINAL_STATUSES = {"resolved", "false_positive"}

# Same plate, same camera, within this window: one alert with a rising
# sighting_count, not a new row per frame (a car waiting at a red light must
# not spam the operator).
ALERT_DEDUP_WINDOW = timedelta(minutes=5)


def _priority_score(priority: str, confidence: float, rung: str) -> float:
    return PRIORITY_WEIGHT.get(priority, 0.5) * confidence * RUNG_WEIGHT.get(rung, 0.5)


async def create_watchlist_entry(
    session: AsyncSession, payload: WatchlistEntryCreate
) -> WatchlistEntry:
    entry = WatchlistEntry(
        plate_normalised=normalise_plate(payload.plate),
        plate_ambiguity_key=ambiguity_key(payload.plate),
        entry_type=payload.entry_type,
        priority=payload.priority,
        case_reference=payload.case_reference,
        requested_by=payload.requested_by,
        notes=payload.notes,
        valid_until=payload.valid_until,
    )
    session.add(entry)
    await session.flush()
    return entry


async def list_watchlist_entries(
    session: AsyncSession, *, active_only: bool = True
) -> list[WatchlistEntry]:
    query = select(WatchlistEntry)
    if active_only:
        query = query.where(WatchlistEntry.active.is_(True))
    result = await session.execute(query.order_by(WatchlistEntry.created_at.desc()))
    return list(result.scalars().all())


async def update_watchlist_entry(
    session: AsyncSession, entry_id: uuid.UUID, *, active: bool | None
) -> WatchlistEntry | None:
    """The Admin Portal's list-management action (docs/03-UX-DESIGN.md §6):
    deactivating an entry by hand, rather than only ever waiting out its
    valid_until expiry."""
    entry = await session.get(WatchlistEntry, entry_id)
    if entry is None:
        return None
    if active is not None:
        entry.active = active
    await session.flush()
    return entry


async def _active_entries_matching(
    session: AsyncSession, *, plate_normalised: str, plate_ambiguity_key: str
) -> list[tuple[WatchlistEntry, str]]:
    """Every active entry this detection matches, paired with the rung that
    matched it. Exact and ambiguity-class are checked independently — a
    detection can match on ambiguity even when a *different* entry also
    matches it exactly, and both should be reported."""
    result = await session.execute(
        select(WatchlistEntry).where(
            WatchlistEntry.active.is_(True),
            (WatchlistEntry.plate_normalised == plate_normalised)
            | (WatchlistEntry.plate_ambiguity_key == plate_ambiguity_key),
        )
    )
    matches: list[tuple[WatchlistEntry, str]] = []
    for entry in result.scalars().all():
        rung = "exact" if entry.plate_normalised == plate_normalised else "ambiguity_class"
        matches.append((entry, rung))
    return matches


async def _upsert_alert(
    session: AsyncSession,
    *,
    entry: WatchlistEntry,
    camera_id: str,
    detection_event_id: str,
    plate_text: str,
    rung: str,
    confidence: float,
    observed_at: datetime,
) -> Alert:
    existing = (
        await session.execute(
            select(Alert).where(
                Alert.watchlist_entry_id == entry.id,
                Alert.camera_id == camera_id,
                Alert.status.not_in(TERMINAL_STATUSES),
                Alert.last_seen_at >= observed_at - ALERT_DEDUP_WINDOW,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.sighting_count += 1
        existing.last_seen_at = max(existing.last_seen_at, observed_at)
        existing.match_confidence = max(existing.match_confidence, confidence)
        existing.priority_score = _priority_score(entry.priority, existing.match_confidence, rung)
        await session.flush()
        return existing

    alert = Alert(
        watchlist_entry_id=entry.id,
        camera_id=camera_id,
        detection_event_id=detection_event_id,
        plate_text=plate_text,
        match_rung=rung,
        match_confidence=confidence,
        priority_score=_priority_score(entry.priority, confidence, rung),
        sighting_count=1,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
    )
    session.add(alert)
    await session.flush()
    return alert


async def correlate_detection(session: AsyncSession, detection: Detection) -> list[Alert]:
    """Check one freshly-ingested detection against every active watchlist
    entry and create/update alerts. Called once per detection, right after
    ingest — see the detections router."""
    matches = await _active_entries_matching(
        session,
        plate_normalised=detection.plate_normalised,
        plate_ambiguity_key=detection.plate_ambiguity_key,
    )
    return [
        await _upsert_alert(
            session,
            entry=entry,
            camera_id=detection.camera_id,
            detection_event_id=detection.event_id,
            plate_text=detection.plate_text,
            rung=rung,
            confidence=detection.plate_confidence,
            observed_at=detection.observed_at,
        )
        for entry, rung in matches
    ]


async def retro_scan(session: AsyncSession, entry: WatchlistEntry) -> list[Alert]:
    """The other half of the BOLO moment: a newly armed entry is checked
    against every detection already on file, not just future ones."""
    result = await session.execute(
        select(Detection).where(
            (Detection.plate_normalised == entry.plate_normalised)
            | (Detection.plate_ambiguity_key == entry.plate_ambiguity_key)
        )
    )
    alerts = []
    for detection in result.scalars().all():
        rung = (
            "exact" if detection.plate_normalised == entry.plate_normalised else "ambiguity_class"
        )
        alerts.append(
            await _upsert_alert(
                session,
                entry=entry,
                camera_id=detection.camera_id,
                detection_event_id=detection.event_id,
                plate_text=detection.plate_text,
                rung=rung,
                confidence=detection.plate_confidence,
                observed_at=detection.observed_at,
            )
        )
    return alerts


async def list_alerts(
    session: AsyncSession, *, status: str | None = None, limit: int = 200
) -> list[Alert]:
    query = select(Alert)
    if status:
        query = query.where(Alert.status == status)
    result = await session.execute(
        query.order_by(Alert.priority_score.desc(), Alert.last_seen_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def update_alert(
    session: AsyncSession, alert_id: uuid.UUID, payload: AlertUpdate
) -> Alert | None:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        return None
    alert.status = payload.status
    if payload.resolved_by:
        alert.resolved_by = payload.resolved_by
    if payload.resolution_note:
        alert.resolution_note = payload.resolution_note
    await session.flush()
    return alert
