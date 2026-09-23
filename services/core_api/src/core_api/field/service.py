"""Field PWA backend support — docs/03-UX-DESIGN.md §5.

Two things a phone on a weak network needs from the server, kept
deliberately cheap:

1. `lookup_plate`: one round trip that answers "is this plate clear, or
   does it need attention, and where was it last seen" — the Field PWA's
   full-screen colour verdict is built entirely from this single response.
2. `record_sighting` / `list_sightings`: the landing spot for the PWA's
   offline outbox once a queued report finally reaches the network.
   Idempotent on `client_report_id` (generated on-device, before the
   report ever reaches the network) so a retried submission after a
   flaky connection never becomes two reports.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import FieldSightingReport
from core_api.detections.service import get_vehicle_route
from core_api.field.schemas import FieldSightingOut
from core_api.watchlist.service import _active_entries_matching
from sentinel_core.plates import ambiguity_key, normalise_plate

__all__ = [
    "PlateLookupResult",
    "list_sightings",
    "lookup_plate",
    "record_sighting",
    "sighting_to_out",
]


class PlateLookupResult:
    def __init__(
        self,
        *,
        plate_normalised: str,
        status: str,
        matches: list[dict[str, object]],
        last_seen_at: datetime | None,
        last_seen_camera_name: str | None,
    ):
        self.plate_normalised = plate_normalised
        self.status = status
        self.matches = matches
        self.last_seen_at = last_seen_at
        self.last_seen_camera_name = last_seen_camera_name


async def lookup_plate(session: AsyncSession, plate_query: str) -> PlateLookupResult:
    plate_normalised = normalise_plate(plate_query)
    matches = await _active_entries_matching(
        session, plate_normalised=plate_normalised, plate_ambiguity_key=ambiguity_key(plate_query)
    )
    route = await get_vehicle_route(session, plate_query)
    last_point = route.points[-1] if route.points else None

    # "clear" only if nothing matches at all; otherwise the single highest-
    # priority entry's type drives the full-screen verdict colour/icon.
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    status = "clear"
    if matches:
        best_entry, _rung = min(matches, key=lambda m: priority_order.get(m[0].priority, 9))
        status = best_entry.entry_type

    return PlateLookupResult(
        plate_normalised=plate_normalised,
        status=status,
        matches=[
            {
                "entry_type": entry.entry_type,
                "priority": entry.priority,
                "match_rung": rung,
                "case_reference": entry.case_reference,
            }
            for entry, rung in matches
        ],
        last_seen_at=last_point.observed_at if last_point else None,
        last_seen_camera_name=last_point.camera_name if last_point else None,
    )


async def find_sighting_by_client_id(
    session: AsyncSession, client_report_id: str
) -> FieldSightingReport | None:
    result = await session.execute(
        select(FieldSightingReport).where(FieldSightingReport.client_report_id == client_report_id)
    )
    return result.scalar_one_or_none()


def _save_photo(reports_dir: Path, report_id: str, photo_bytes: bytes) -> str:
    reports_dir.mkdir(parents=True, exist_ok=True)
    # sha256-derived filename: two officers photographing the same scene
    # moments apart never collide, and the name itself is a cheap integrity
    # fingerprint without a separate manifest (unlike sealed evidence
    # clips, a field snapshot isn't chain-of-custody evidence on its own).
    digest = hashlib.sha256(photo_bytes).hexdigest()[:16]
    path = reports_dir / f"{report_id}-{digest}.jpg"
    path.write_bytes(photo_bytes)
    return str(path)


async def record_sighting(
    session: AsyncSession,
    *,
    reports_dir: Path,
    client_report_id: str,
    reported_by: str,
    plate_text: str,
    lat: float | None,
    lon: float | None,
    notes: str | None,
    photo_bytes: bytes | None,
) -> tuple[FieldSightingReport, bool]:
    """Returns (report, created) — `created` is False when this
    client_report_id was already recorded, so the caller can respond 200
    instead of 201 without doing anything twice."""
    existing = await find_sighting_by_client_id(session, client_report_id)
    if existing is not None:
        return existing, False

    report = FieldSightingReport(
        client_report_id=client_report_id,
        reported_by=reported_by,
        plate_text=plate_text,
        lat=lat,
        lon=lon,
        notes=notes,
    )
    session.add(report)
    await session.flush()

    if photo_bytes:
        report.photo_path = await asyncio.to_thread(
            _save_photo, reports_dir, str(report.id), photo_bytes
        )

    return report, True


async def list_sightings(session: AsyncSession, *, limit: int = 100) -> list[FieldSightingReport]:
    result = await session.execute(
        select(FieldSightingReport).order_by(FieldSightingReport.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


def sighting_to_out(report: FieldSightingReport) -> FieldSightingOut:
    return FieldSightingOut(
        id=report.id,
        client_report_id=report.client_report_id,
        reported_by=report.reported_by,
        plate_text=report.plate_text,
        lat=report.lat,
        lon=report.lon,
        notes=report.notes,
        has_photo=report.photo_path is not None,
        created_at=report.created_at,
    )
