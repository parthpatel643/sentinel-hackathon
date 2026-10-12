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

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Alert, Detection, WatchlistEntry
from core_api.watchlist.schemas import AlertUpdate, WatchlistEntryCreate
from sentinel_core.plates import ambiguity_key, normalise_plate

__all__ = [
    "ALERT_DEDUP_WINDOW",
    "PRIORITY_WEIGHT",
    "SAME_PASS_TOLERANCE",
    "arm_watchlist_entry",
    "correlate_detection",
    "create_watchlist_entry",
    "list_alerts",
    "list_watchlist_entries",
    "retro_scan",
    "sightings_on_file",
    "update_alert",
]

PRIORITY_WEIGHT = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
RUNG_WEIGHT = {"exact": 1.0, "ambiguity_class": 0.7}
TERMINAL_STATUSES = {"resolved", "false_positive"}

# Same plate, same camera, within this window: one alert with a rising
# sighting_count, not a new row per frame (a car waiting at a red light must
# not spam the operator).
ALERT_DEDUP_WINDOW = timedelta(minutes=5)

# A sighting the camera's own clock puts within this of a pass already
# alerted on is that pass delivered again, however much later it reached us:
# a stream reconnect replaying its buffer, an edge backlog, or a recording on
# a loop. Wide enough for a car held at a signal across reads; far narrower
# than any gap between two real passes. Only verified clock reads count
# (the clock reader rejects a frozen or jumping overlay), so a stuck camera
# clock cannot silence a genuine second pass.
SAME_PASS_TOLERANCE = timedelta(minutes=1)


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


async def arm_watchlist_entry(
    session: AsyncSession, payload: WatchlistEntryCreate
) -> tuple[WatchlistEntry, bool]:
    """The active entry already watching this plate for this reason, or a new
    one — `(entry, created)`.

    Found in a manual test: one vehicle armed seven times in under a minute
    (the button came back while the search refreshed). Every active entry
    raises its own alert per sighting, so seven entries meant seven copies of
    every alert. A transaction-scoped advisory lock on the plate and reason
    makes concurrent requests — a double click — queue behind each other, so
    the second sees the first's entry instead of racing it."""
    plate_normalised = normalise_plate(payload.plate)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"watchlist:{plate_normalised}:{payload.entry_type}"},
    )
    existing = (
        await session.execute(
            select(WatchlistEntry)
            .where(
                WatchlistEntry.active.is_(True),
                WatchlistEntry.plate_normalised == plate_normalised,
                WatchlistEntry.entry_type == payload.entry_type,
            )
            .order_by(WatchlistEntry.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    return await create_watchlist_entry(session, payload), True


async def sightings_on_file(session: AsyncSession, entry: WatchlistEntry) -> int:
    """Sightings already counted on this entry's alerts."""
    total = await session.scalar(
        select(func.coalesce(func.sum(Alert.sighting_count), 0)).where(
            Alert.watchlist_entry_id == entry.id
        )
    )
    return int(total or 0)


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


async def _pass_already_alerted(
    session: AsyncSession, *, entry: WatchlistEntry, camera_id: str, camera_time: datetime
) -> bool:
    """Whether an alert on this entry and camera, open or closed, already
    covers this moment on the camera's clock. A closed one counts too: a
    resolved alert must not come back because its footage was replayed."""
    span_start = func.coalesce(Alert.first_seen_camera_time, Alert.last_seen_camera_time)
    span_end = func.coalesce(Alert.last_seen_camera_time, Alert.first_seen_camera_time)
    found = await session.scalar(
        select(Alert.id)
        .where(
            Alert.watchlist_entry_id == entry.id,
            Alert.camera_id == camera_id,
            span_start <= camera_time + SAME_PASS_TOLERANCE,
            span_end >= camera_time - SAME_PASS_TOLERANCE,
        )
        .limit(1)
    )
    return found is not None


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
    camera_time: datetime | None,
) -> Alert | None:
    """The alert this sighting raised or joined, or `None` when the camera's
    clock shows it is a pass already alerted on, delivered again — that is
    not news, so nothing changes and nothing is announced."""
    # The window is checked on both sides: a sighting merges into an open
    # alert only if it falls within the dedup window of that alert's span.
    # Checking only `last_seen_at` let an older sighting (retro-scan, a
    # delayed upload) fold into an alert from hours later.
    existing = (
        (
            await session.execute(
                select(Alert)
                .where(
                    Alert.watchlist_entry_id == entry.id,
                    Alert.camera_id == camera_id,
                    Alert.status.not_in(TERMINAL_STATUSES),
                    Alert.last_seen_at >= observed_at - ALERT_DEDUP_WINDOW,
                    Alert.first_seen_at <= observed_at + ALERT_DEDUP_WINDOW,
                )
                .order_by(Alert.last_seen_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    if existing is not None:
        existing.sighting_count += 1
        # Processing time decides which sighting is first and last; the
        # camera's clock on that sighting is what is reported, unknown or not.
        if observed_at < existing.first_seen_at:
            existing.first_seen_at = observed_at
            existing.first_seen_camera_time = camera_time
        if observed_at > existing.last_seen_at:
            existing.last_seen_at = observed_at
            existing.last_seen_camera_time = camera_time
        existing.match_confidence = max(existing.match_confidence, confidence)
        existing.priority_score = _priority_score(entry.priority, existing.match_confidence, rung)
        await session.flush()
        return existing

    if camera_time is not None and await _pass_already_alerted(
        session, entry=entry, camera_id=camera_id, camera_time=camera_time
    ):
        return None

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
        first_seen_camera_time=camera_time,
        last_seen_camera_time=camera_time,
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
    alerts = [
        await _upsert_alert(
            session,
            entry=entry,
            camera_id=detection.camera_id,
            detection_event_id=detection.event_id,
            plate_text=detection.plate_text,
            rung=rung,
            confidence=detection.plate_confidence,
            observed_at=detection.observed_at,
            camera_time=detection.camera_time,
        )
        for entry, rung in matches
    ]
    return [alert for alert in alerts if alert is not None]


async def retro_scan(session: AsyncSession, entry: WatchlistEntry) -> list[Alert]:
    """The other half of the BOLO moment: a newly armed entry is checked
    against every detection already on file, not just future ones."""
    result = await session.execute(
        select(Detection)
        .where(
            (Detection.plate_normalised == entry.plate_normalised)
            | (Detection.plate_ambiguity_key == entry.plate_ambiguity_key)
        )
        # In the scene's order, so sightings merge into alerts exactly as
        # they would have had the entry been armed before they happened.
        .order_by(Detection.observed_at.asc(), Detection.event_id.asc())
    )
    alerts: dict[uuid.UUID, Alert] = {}
    for detection in result.scalars().all():
        rung = (
            "exact" if detection.plate_normalised == entry.plate_normalised else "ambiguity_class"
        )
        alert = await _upsert_alert(
            session,
            entry=entry,
            camera_id=detection.camera_id,
            detection_event_id=detection.event_id,
            plate_text=detection.plate_text,
            rung=rung,
            confidence=detection.plate_confidence,
            observed_at=detection.observed_at,
            camera_time=detection.camera_time,
        )
        if alert is not None:
            alerts[alert.id] = alert
    # One entry per alert, however many sightings merged into it.
    return list(alerts.values())


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
