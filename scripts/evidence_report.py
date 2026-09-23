#!/usr/bin/env python3
"""Auto-generated evidence report — docs/05-DELIVERY-PLAN.md M14:
"overnight multi-hour run across the full grid; auto-generated evidence
report".

docs/05-DELIVERY-PLAN.md's weekly rhythm says it plainly: "Claims backed by
artefacts win; adjectives do not." This script turns whatever the platform
actually did into one such artefact — it reads the live database and the
relay, computes the numbers, and writes them out. Every figure here is
measured, never estimated, and any metric that cannot be computed from the
data present says so rather than showing a zero that reads like a result.

Usage:
    uv run --package core_api python scripts/evidence_report.py
    uv run --package core_api python scripts/evidence_report.py \
        --since 2026-09-23T10:38:44Z \
        --out evidence/M14-EVIDENCE-RUN.md --csv evidence/m14-detections.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.base import get_sessionmaker
from core_api.db.models import (
    Alert,
    Camera,
    Detection,
    WatchlistEntry,
    Zone,
    ZoneEvent,
)
from sentinel_core.config import Settings

UNAVAILABLE = "_not measurable from this run_"


@dataclass
class Section:
    title: str
    rows: list[tuple[str, str]] = field(default_factory=list)
    note: str = ""

    def add(self, label: str, value: Any) -> None:
        self.rows.append((label, str(value)))


def _fmt_duration(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _pct(part: int, whole: int) -> str:
    if whole == 0:
        return "—"
    return f"{100.0 * part / whole:.1f}%"


def _quantile(values: list[float], q: float) -> float:
    """Plain nearest-rank quantile. Deliberately not numpy: this script is
    run on whatever machine has the database, and one fewer import that can
    be missing is one fewer reason an evidence run fails at the last step."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


async def _relay_paths(settings: Settings) -> list[dict[str, Any]]:
    """Ask our own relay what it is actually serving. Best effort: the report
    is still worth producing if the relay is down, so this degrades to an
    empty list rather than aborting the run."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.relay_api_url}/v3/paths/list")
            response.raise_for_status()
            items: list[dict[str, Any]] = response.json().get("items", [])
            return items
    except (httpx.HTTPError, ValueError):
        return []


async def _collect(
    session: AsyncSession, since: datetime | None
) -> tuple[list[Section], list[dict[str, Any]]]:
    sections: list[Section] = []

    detection_filter = [Detection.observed_at >= since] if since else []

    # --- Run scope ---------------------------------------------------------
    first_obs = await session.scalar(
        select(func.min(Detection.observed_at)).where(*detection_filter)
    )
    last_obs = await session.scalar(
        select(func.max(Detection.observed_at)).where(*detection_filter)
    )
    total_detections = (
        await session.scalar(select(func.count()).select_from(Detection).where(*detection_filter))
    ) or 0

    scope = Section("Run scope")
    if first_obs and last_obs:
        window = last_obs - first_obs
        scope.add("First detection (observed_at)", first_obs.isoformat())
        scope.add("Last detection (observed_at)", last_obs.isoformat())
        scope.add("Analysed window", _fmt_duration(window))
    else:
        scope.add("Analysed window", "no detections in range")
        window = timedelta(0)
    scope.add("Report generated", datetime.now(UTC).isoformat())
    scope.note = (
        "Timestamps are `observed_at` — derived from the stream's own PTS plus its epoch "
        "anchor, never frame arrival time (ADR-005). A run's window is therefore the "
        "footage's timeline, not the wall clock of the machine that processed it."
    )
    sections.append(scope)

    # --- Camera fleet ------------------------------------------------------
    cameras = list((await session.scalars(select(Camera))).all())
    by_status = Counter(c.status for c in cameras)
    by_source = Counter(c.source for c in cameras)
    analysed = set(
        (
            await session.scalars(
                select(Detection.camera_id).where(*detection_filter).distinct()
            )
        ).all()
    )

    fleet = Section("Camera fleet")
    fleet.add("Cameras registered", len(cameras))
    for status, count in sorted(by_status.items()):
        fleet.add(f"  status = {status}", f"{count} ({_pct(count, len(cameras))})")
    for source, count in sorted(by_source.items()):
        fleet.add(f"  source = {source}", count)
    fleet.add("Cameras that produced detections", len(analysed))
    fleet.note = (
        "A camera can be registered and healthy without producing detections — the grid is "
        "onboarded in full, while analysis runs on the subset the worker was asked to open "
        "(the integrator guide's \"pace your load\" guidance)."
    )
    sections.append(fleet)

    # --- Throughput --------------------------------------------------------
    throughput = Section("Detection throughput")
    throughput.add("Total detections", total_detections)
    distinct_plates = (
        await session.scalar(
            select(func.count(func.distinct(Detection.plate_normalised))).where(*detection_filter)
        )
    ) or 0
    throughput.add("Distinct normalised plates", distinct_plates)
    if window.total_seconds() > 0:
        per_hour = total_detections / (window.total_seconds() / 3600)
        throughput.add("Detections per hour (across analysed cameras)", f"{per_hour:.1f}")
    else:
        throughput.add("Detections per hour", UNAVAILABLE)
    if analysed:
        throughput.add(
            "Mean detections per analysed camera", f"{total_detections / len(analysed):.1f}"
        )
    sections.append(throughput)

    # --- Read quality ------------------------------------------------------
    rows = list(
        (
            await session.execute(
                select(
                    Detection.camera_id,
                    Detection.plate_text,
                    Detection.plate_normalised,
                    Detection.plate_confidence,
                    Detection.format_valid,
                    Detection.frames_voted,
                    Detection.vehicle_class,
                    Detection.vehicle_colour,
                    Detection.observed_at,
                    Detection.created_at,
                ).where(*detection_filter)
            )
        ).all()
    )

    quality = Section("Read quality")
    if rows:
        confidences = [float(r.plate_confidence) for r in rows]
        votes = [int(r.frames_voted) for r in rows]
        valid = sum(1 for r in rows if r.format_valid)
        quality.add("Mean plate confidence", f"{statistics.fmean(confidences):.3f}")
        quality.add("Median plate confidence", f"{statistics.median(confidences):.3f}")
        quality.add(
            "p10 / p90 confidence",
            f"{_quantile(confidences, 0.1):.3f} / {_quantile(confidences, 0.9):.3f}",
        )
        quality.add(
            "Reads passing Indian-plate format validation",
            f"{valid} ({_pct(valid, len(rows))})",
        )
        quality.add("Mean frames voted per read", f"{statistics.fmean(votes):.1f}")
        quality.add("Max frames voted", max(votes))
    else:
        quality.add("Plate confidence", UNAVAILABLE)
    quality.note = (
        "`format_valid` is not an accuracy figure and must not be read as one. It reports "
        "whether a read matches Indian plate grammar; a partial read from distant or angled "
        "traffic footage correctly fails it. A true accuracy number needs a hand-labelled "
        "holdout, which this project does not yet have — see "
        "`evidence/M2-SYNTHETIC-GRID-DISCONTINUITY-FINDING.md`."
    )
    sections.append(quality)

    # --- Secondary analytics ----------------------------------------------
    analytics = Section("Secondary analytics (M13)")
    classes = Counter(r.vehicle_class for r in rows if r.vehicle_class)
    colours = Counter(r.vehicle_colour for r in rows if r.vehicle_colour)
    analytics.add(
        "Reads with a vehicle class",
        f"{sum(classes.values())} ({_pct(sum(classes.values()), len(rows))})",
    )
    for name, count in classes.most_common(6):
        analytics.add(f"  class = {name}", count)
    analytics.add(
        "Reads with a vehicle colour",
        f"{sum(colours.values())} ({_pct(sum(colours.values()), len(rows))})",
    )
    for name, count in colours.most_common(8):
        analytics.add(f"  colour = {name}", count)

    zones = (await session.scalar(select(func.count()).select_from(Zone))) or 0
    zone_events = list((await session.scalars(select(ZoneEvent))).all())
    analytics.add("Zones configured", zones)
    analytics.add("Zone events fired", len(zone_events))
    for rule, count in Counter(z.rule_type for z in zone_events).most_common():
        analytics.add(f"  rule = {rule}", count)
    tamper = Counter(c.tamper_status for c in cameras if c.tamper_status)
    for status, count in tamper.most_common():
        analytics.add(f"Tamper status = {status}", count)
    analytics.note = (
        "Vehicle colour is a coarse HSV heuristic, not a trained classifier, and "
        "coarse-make is deliberately out of scope — see `docs/09-SECONDARY-ANALYTICS.md`."
    )
    sections.append(analytics)

    # --- Resilience --------------------------------------------------------
    resilience = Section("Resilience")
    total_reconnects = sum(c.reconnects or 0 for c in cameras)
    total_disc = sum(c.discontinuities or 0 for c in cameras)
    resilience.add("Total reconnects across the fleet", total_reconnects)
    resilience.add("Total stream discontinuities observed", total_disc)
    worst = sorted(cameras, key=lambda c: c.reconnects or 0, reverse=True)[:5]
    for camera in worst:
        if camera.reconnects:
            resilience.add(f"  {camera.camera_id} reconnects", camera.reconnects)
    resilience.note = (
        "Reconnects are expected, not a fault: the guide states feeds are supervised and "
        "may restart. What matters is that they are counted and recovered from "
        "unattended — exercised directly by `scripts/chaos_drill.py`."
    )
    sections.append(resilience)

    # --- Ingest latency ----------------------------------------------------
    latency = Section("Ingest latency")
    lags = [
        (r.created_at - r.observed_at).total_seconds()
        for r in rows
        if r.created_at and r.observed_at
    ]
    positive = [lag for lag in lags if lag >= 0]
    if positive:
        latency.add("Median observed_at -> stored", f"{statistics.median(positive):.1f}s")
        latency.add("p90 observed_at -> stored", f"{_quantile(positive, 0.9):.1f}s")
    else:
        latency.add("observed_at -> stored", UNAVAILABLE)
    latency.note = (
        "This is end-to-end lag from the moment in the footage to the row being committed, "
        "covering detection, tracking, OCR, temporal voting and the HTTP write. It is not a "
        "model inference time. Negative lags are excluded: they mean the footage's own "
        "timeline is ahead of this machine's clock, which says nothing about the pipeline."
    )
    sections.append(latency)

    # --- Watchlist and alerts ---------------------------------------------
    alerting = Section("Watchlist and alerting")
    alerting.add(
        "Watchlist entries",
        (await session.scalar(select(func.count()).select_from(WatchlistEntry))) or 0,
    )
    alerts = list((await session.scalars(select(Alert))).all())
    alerting.add("Alerts raised", len(alerts))
    for rung, count in Counter(a.match_rung for a in alerts).most_common():
        alerting.add(f"  match rung = {rung}", count)
    for status, count in Counter(a.status for a in alerts).most_common():
        alerting.add(f"  status = {status}", count)
    sections.append(alerting)

    csv_rows = [
        {
            "camera_id": r.camera_id,
            "observed_at": r.observed_at.isoformat(),
            "plate_text": r.plate_text,
            "plate_normalised": r.plate_normalised,
            "plate_confidence": f"{float(r.plate_confidence):.4f}",
            "format_valid": r.format_valid,
            "frames_voted": r.frames_voted,
            "vehicle_class": r.vehicle_class or "",
            "vehicle_colour": r.vehicle_colour or "",
        }
        for r in rows
    ]
    return sections, csv_rows


def _render(
    sections: list[Section], relay_paths: list[dict[str, Any]], since: datetime | None
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# M14 Evidence Run",
        "",
        f"Auto-generated by `scripts/evidence_report.py` on {now}.",
        "",
        "Every number below is read out of the running system — the live database and the "
        "local relay — at the moment of generation. Nothing here is hand-entered, and "
        "metrics that the run cannot support are marked as such rather than shown as zero.",
        "",
    ]
    if since:
        lines += [f"Scope: detections with `observed_at >= {since.isoformat()}`.", ""]
    else:
        lines += ["Scope: all detections currently in the database.", ""]

    for section in sections:
        lines += [f"## {section.title}", "", "| Metric | Value |", "|---|---|"]
        lines += [f"| {label} | {value} |" for label, value in section.rows]
        lines.append("")
        if section.note:
            lines += [f"> {section.note}", ""]

    lines += ["## Relay paths currently served", ""]
    if relay_paths:
        lines += ["| Path | Ready | Readers |", "|---|---|---|"]
        for path in relay_paths:
            lines.append(
                f"| `{path.get('name')}` | {path.get('ready')} | {len(path.get('readers') or [])} |"
            )
    else:
        lines.append("_Relay not reachable at generation time._")
    lines.append("")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        help="ISO-8601 instant; only count detections observed at or after it",
    )
    parser.add_argument("--out", type=Path, default=Path("evidence/M14-EVIDENCE-RUN.md"))
    parser.add_argument("--csv", type=Path, help="also write the raw detection rows here")
    args = parser.parse_args()

    since: datetime | None = None
    if args.since:
        since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))

    settings = Settings()
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        sections, csv_rows = await _collect(session, since)
    relay_paths = await _relay_paths(settings)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_render(sections, relay_paths, since))
    print(f"report written to {args.out} ({len(csv_rows)} detection(s) summarised)")

    if args.csv and csv_rows:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"raw rows written to {args.csv}")
    elif args.csv:
        print("no detection rows to write to CSV")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
