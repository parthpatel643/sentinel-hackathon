"""Bulk CSV camera onboarding.

Matches the UX design's wizard flow (03-UX-DESIGN.md section 4.6): parse,
validate every row independently, preview via dry-run, commit only when the
operator confirms. One malformed row must never block the other 999.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.registry.schemas import GeoPointOut, StreamProfileIn
from core_api.registry.service import upsert_camera

__all__ = ["BulkImportResult", "BulkImportRowResult", "parse_and_import_csv"]

REQUIRED_COLUMNS = {"camera_id", "name"}
OPTIONAL_COLUMNS = {
    "driver_id",
    "department_name",
    "site_name",
    "lat",
    "lon",
    "tier",
    "protocol",
    "url",
    "codec",
    "width",
    "height",
    "declared_fps",
}


@dataclass(slots=True)
class BulkImportRowResult:
    row_number: int
    camera_id: str | None
    ok: bool
    error: str | None = None


@dataclass(slots=True)
class BulkImportResult:
    dry_run: bool
    total_rows: int
    succeeded: int
    failed: int
    rows: list[BulkImportRowResult] = field(default_factory=list)


@dataclass(slots=True)
class ParsedCameraRow:
    """A properly-typed row, as opposed to `dict[str, object]` — the whole
    point of this dataclass is that `upsert_camera(**row_fields)`-style
    passing needs each field typed correctly, not just present."""

    camera_id: str
    name: str
    driver_id: str
    department_name: str | None
    site_name: str | None
    location: GeoPointOut | None
    tier: str
    profiles: list[StreamProfileIn]


def _parse_row(raw: dict[str, str]) -> tuple[ParsedCameraRow | None, str | None]:
    """Validate one row. Returns (parsed_row, error) — error is None on
    success. Never raises: a bad row is data, not a program failure."""
    missing = REQUIRED_COLUMNS - {k for k, v in raw.items() if v and v.strip()}
    if missing:
        return None, f"missing required column(s): {sorted(missing)}"

    camera_id = raw["camera_id"].strip()
    name = raw["name"].strip()
    if not camera_id:
        return None, "camera_id is blank"

    location: GeoPointOut | None = None
    lat_raw, lon_raw = raw.get("lat", "").strip(), raw.get("lon", "").strip()
    if lat_raw or lon_raw:
        try:
            location = GeoPointOut(lat=float(lat_raw), lon=float(lon_raw))
        except ValueError:
            return None, f"lat/lon are not both valid numbers: {lat_raw!r}, {lon_raw!r}"

    profiles: list[StreamProfileIn] = []
    if raw.get("url", "").strip():
        try:
            profiles.append(
                StreamProfileIn(
                    protocol=raw.get("protocol", "rtsp").strip() or "rtsp",
                    url=raw["url"].strip(),
                    codec=raw.get("codec", "").strip() or None,
                    width=int(raw["width"]) if raw.get("width", "").strip() else None,
                    height=int(raw["height"]) if raw.get("height", "").strip() else None,
                    declared_fps=(
                        float(raw["declared_fps"]) if raw.get("declared_fps", "").strip() else None
                    ),
                )
            )
        except ValueError as exc:
            return None, f"invalid stream profile column: {exc}"

    return (
        ParsedCameraRow(
            camera_id=camera_id,
            name=name,
            driver_id=raw.get("driver_id", "").strip() or "rtsp",
            department_name=raw.get("department_name", "").strip() or None,
            site_name=raw.get("site_name", "").strip() or None,
            location=location,
            tier=raw.get("tier", "").strip() or "b_sampled",
            profiles=profiles,
        ),
        None,
    )


async def parse_and_import_csv(
    session: AsyncSession, csv_text: str, *, dry_run: bool
) -> BulkImportResult:
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return BulkImportResult(dry_run=dry_run, total_rows=0, succeeded=0, failed=0)

    unknown_required = REQUIRED_COLUMNS - set(reader.fieldnames)
    if unknown_required:
        return BulkImportResult(
            dry_run=dry_run,
            total_rows=0,
            succeeded=0,
            failed=1,
            rows=[
                BulkImportRowResult(
                    row_number=0,
                    camera_id=None,
                    ok=False,
                    error=f"CSV is missing required column(s): {sorted(unknown_required)}",
                )
            ],
        )

    results: list[BulkImportRowResult] = []
    for row_number, raw in enumerate(reader, start=1):
        parsed, error = _parse_row(raw)
        if error is not None or parsed is None:
            results.append(
                BulkImportRowResult(
                    row_number=row_number, camera_id=raw.get("camera_id"), ok=False, error=error
                )
            )
            continue

        if not dry_run:
            try:
                await upsert_camera(
                    session,
                    camera_id=parsed.camera_id,
                    name=parsed.name,
                    driver_id=parsed.driver_id,
                    department_name=parsed.department_name,
                    site_name=parsed.site_name,
                    location=parsed.location,
                    tier=parsed.tier,
                    status="unknown",
                    source="bulk_csv",
                    attributes={},
                    profiles=parsed.profiles,
                )
            except Exception as exc:
                results.append(
                    BulkImportRowResult(
                        row_number=row_number,
                        camera_id=parsed.camera_id,
                        ok=False,
                        error=str(exc),
                    )
                )
                continue

        results.append(
            BulkImportRowResult(row_number=row_number, camera_id=parsed.camera_id, ok=True)
        )

    succeeded = sum(1 for r in results if r.ok)
    return BulkImportResult(
        dry_run=dry_run,
        total_rows=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        rows=results,
    )
