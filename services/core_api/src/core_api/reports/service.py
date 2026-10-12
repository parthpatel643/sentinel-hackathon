"""Movement Report export: PDF + CSV + a hash manifest binding them together,
per docs/01-ARCHITECTURE.md section 6.3 ("a shareable, exportable Movement
Report — map, ordered table of location + timestamp, snapshot per hop,
confidence per hop, and a hash manifest. This is literally the eval-day
deliverable.") and section 6.5's evidence-bundle pattern (media + manifest +
PDF report, suitable for attaching to a case file).

The three artifacts are generated once and zipped together so the manifest's
hashes are always computed over the exact bytes shipped in the same
download — there is no separate "regenerate the manifest later" step that
could ever disagree with what a jury or officer actually opens.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import zipfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

from fpdf import FPDF

from core_api.detections.schemas import RoutePoint, VehicleRoute
from core_api.reports.basemap import Basemap

__all__ = ["MAP_ASPECT", "build_movement_report_zip"]

# Evidence is stored in UTC; the officers and jury reading it work in IST.
# India has no DST, so a fixed offset is exact and needs no tz database.
IST = timezone(timedelta(hours=5, minutes=30), "IST")
_HUMAN_TIME = "%d %b %Y, %H:%M:%S"


def _ist(moment: datetime) -> str:
    return moment.astimezone(IST).strftime(_HUMAN_TIME)


# Every sighting time in this report is the clock the camera burned into the
# evidence frame. A sighting whose clock could not be read says so, and is
# given no other time in its place.
TIME_UNKNOWN = "time unknown - camera clock unreadable"


def _camera_ist(point: RoutePoint) -> str:
    return _ist(point.camera_time) if point.camera_time else TIME_UNKNOWN


_CSV_HEADER = [
    "hop",
    "camera_id",
    "camera_name",
    "latitude",
    "longitude",
    "camera_clock",
    "camera_time_utc",
    "camera_time_ist",
    "plate_text",
    "plate_confidence",
    "match_rung",
    "confirmed",
    "implied_speed_kmh",
    "infeasible",
    "snapshot_uri",
]


def _render_csv(route: VehicleRoute) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_HEADER)
    rows = [(str(i), p) for i, p in enumerate(route.points, start=1)]
    rows += [(f"U{i}", p) for i, p in enumerate(route.untimed, start=1)]
    for hop, point in rows:
        writer.writerow(
            [
                hop,
                point.camera_id,
                point.camera_name,
                point.location.lat if point.location else "",
                point.location.lon if point.location else "",
                "read" if point.camera_time else "unreadable",
                point.camera_time.isoformat() if point.camera_time else "",
                point.camera_time.astimezone(IST).isoformat() if point.camera_time else "",
                point.plate_text,
                f"{point.plate_confidence:.3f}",
                point.match_rung,
                point.confirmed,
                "" if point.implied_speed_kmh is None else point.implied_speed_kmh,
                point.infeasible,
                point.snapshot_uri or "",
            ]
        )
    return buffer.getvalue().encode("utf-8")


_ROUTE_BLUE = (36, 86, 214)
_PROBABLE_AMBER = (196, 120, 20)
_NICE_KM = (0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200)
_KM_PER_DEGREE_LAT = 111.32
# The route frame on a landscape A4 page with fpdf's 10 mm margins.
_MAP_W_MM = 277.0
_MAP_H_MM = 88.0
MAP_ASPECT = _MAP_W_MM / _MAP_H_MM


def _draw_route_sketch(
    pdf: FPDF,
    route: VehicleRoute,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    basemap: Basemap | None = None,
) -> None:
    """The route at the cameras' coordinates — numbered hops, solid for
    confirmed and dashed for probable, a scale bar and north — over a street
    map when one was fetched at export (reports/basemap.py), otherwise to
    scale on a blank frame, so the report still renders with no internet."""
    located = [(i, p) for i, p in enumerate(route.points, start=1) if p.location is not None]
    if not located:
        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.3)
        pdf.rect(x, y, w, h)
        pdf.set_xy(x, y + h / 2 - 3)
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(w, 6, "No sighting has camera coordinates to place on a map.", align="C")
        return

    if basemap is not None:
        pdf.image(io.BytesIO(basemap.image_png), x=x, y=y, w=w, h=h)
        mid = located[0][1].location
        assert mid is not None
        mm_per_km = 1000 / basemap.metres_per_pixel(mid.lat) * (w / basemap.width_px)

        def on_map(point: RoutePoint) -> tuple[float, float]:
            assert point.location is not None and basemap is not None
            fx, fy = basemap.place(point.location.lat, point.location.lon)
            return x + fx * w, y + fy * h

        _draw_route_marks(pdf, located, on_map, mm_per_km, x=x, y=y, w=w, h=h)
        pdf.set_font("Helvetica", "", 6.5)
        label_w = pdf.get_string_width(basemap.attribution) + 3
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(60, 60, 60)
        pdf.set_xy(x + w - label_w, y + h - 4)
        pdf.cell(label_w, 4, basemap.attribution, align="C", fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.3)
        pdf.rect(x, y, w, h)
        return

    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, w, h)
    lats = [p.location.lat for _, p in located if p.location]
    lons = [p.location.lon for _, p in located if p.location]
    mid_lat = (min(lats) + max(lats)) / 2
    lon_scale = math.cos(math.radians(mid_lat))
    # Equirectangular, in km: accurate to well under 1% at district scale.
    xs_km = [(lon - min(lons)) * lon_scale * _KM_PER_DEGREE_LAT for lon in lons]
    ys_km = [(lat - min(lats)) * _KM_PER_DEGREE_LAT for lat in lats]
    span_km = max(max(xs_km), max(ys_km), 0.2)
    pad = 14.0
    mm_per_km = min(
        (w - 2 * pad) / max(max(xs_km), span_km * 0.05, 0.2),
        (h - 2 * pad) / max(max(ys_km), span_km * 0.05, 0.2),
    )
    off_x = x + (w - max(xs_km) * mm_per_km) / 2
    off_y = y + (h - max(ys_km) * mm_per_km) / 2

    def place(point: RoutePoint) -> tuple[float, float]:
        assert point.location is not None
        px = (point.location.lon - min(lons)) * lon_scale * _KM_PER_DEGREE_LAT
        py = (point.location.lat - min(lats)) * _KM_PER_DEGREE_LAT
        return off_x + px * mm_per_km, off_y + (max(ys_km) - py) * mm_per_km

    _draw_route_marks(pdf, located, place, mm_per_km, x=x, y=y, w=w, h=h)


def _draw_route_marks(
    pdf: FPDF,
    located: list[tuple[int, RoutePoint]],
    place: Callable[[RoutePoint], tuple[float, float]],
    mm_per_km: float,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    """Hops, numbered markers, scale bar and north arrow, wherever `place`
    puts each sighting."""
    pdf.set_line_width(0.7)
    for (_, a), (_, b) in pairwise(located):
        colour = _ROUTE_BLUE if b.confirmed else _PROBABLE_AMBER
        pdf.set_draw_color(*colour)
        pdf.set_dash_pattern(dash=0 if b.confirmed else 1.5, gap=0 if b.confirmed else 1.2)
        (ax, ay), (bx, by) = place(a), place(b)
        pdf.line(ax, ay, bx, by)
    pdf.set_dash_pattern()

    # One marker per camera position, listing every hop seen there.
    by_position: dict[tuple[float, float], list[int]] = {}
    names: dict[tuple[float, float], str] = {}
    confirmed_at: dict[tuple[float, float], bool] = {}
    for index, point in located:
        key = place(point)
        by_position.setdefault(key, []).append(index)
        names[key] = point.camera_name
        confirmed_at[key] = confirmed_at.get(key, False) or point.confirmed
    for (px, py), hops in by_position.items():
        pdf.set_fill_color(*(_ROUTE_BLUE if confirmed_at[(px, py)] else _PROBABLE_AMBER))
        pdf.set_draw_color(255, 255, 255)
        pdf.set_line_width(0.4)
        pdf.circle(px, py, 3.2, style="FD")
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(px - 3.2, py - 1.8)
        pdf.cell(6.4, 3.6, str(hops[0]), align="C")
        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "B", 7.5)
        label = f"{', '.join(str(h) for h in hops)}  {names[(px, py)][:30]}"
        label_w = pdf.get_string_width(label) + 2
        pdf.set_fill_color(255, 255, 255)
        pdf.set_xy(min(px + 4.5, x + w - label_w - 2), py - 1.8)
        pdf.cell(label_w, 3.6, label, fill=True)

    # Scale bar: the nice distance closest to 30 mm, on a white plate so it
    # reads over a street map.
    bar_km = min(_NICE_KM, key=lambda km: abs(km * mm_per_km - 30))
    bar_mm = bar_km * mm_per_km
    bx, by = x + 6, y + h - 6
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(bx - 3, by - 6, bar_mm + 6, 8.5, style="F")
    pdf.rect(x + w - 12, y + 3, 8, 15, style="F")
    pdf.set_draw_color(40, 40, 40)
    pdf.set_line_width(0.6)
    pdf.line(bx, by, bx + bar_mm, by)
    pdf.line(bx, by - 1.2, bx, by + 1.2)
    pdf.line(bx + bar_mm, by - 1.2, bx + bar_mm, by + 1.2)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(bx, by - 5)
    pdf.cell(bar_mm, 3.5, f"{bar_km:g} km", align="C")
    # North.
    nx, ny = x + w - 8, y + 6
    pdf.line(nx, ny + 7, nx, ny)
    pdf.line(nx, ny, nx - 1.5, ny + 2.5)
    pdf.line(nx, ny, nx + 1.5, ny + 2.5)
    pdf.set_xy(nx - 3, ny + 7.5)
    pdf.cell(6, 3.5, "N", align="C")
    pdf.set_text_color(0, 0, 0)


def _render_evidence(pdf: FPDF, route: VehicleRoute, snapshots: Mapping[str, Path]) -> None:
    """A face-blurred snapshot per sighting, captioned — the frame behind each
    line of the tables, so the report stands on its own without the console.
    The time in each caption is the clock visible in that frame."""
    hops = [(str(i), p) for i, p in enumerate(route.points, start=1)]
    hops += [(f"U{i}", p) for i, p in enumerate(route.untimed, start=1)]
    hops = [(label, p) for label, p in hops if p.event_id in snapshots]
    if not hops:
        return
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(
        0, 8, "Evidence - one frame per sighting (faces blurred)", new_x="LMARGIN", new_y="NEXT"
    )
    width, gap = 85.0, 6.0
    per_row = 3
    for slot, (index, point) in enumerate(hops):
        column = slot % per_row
        if column == 0:
            row_y = pdf.get_y() + 2
            if row_y + 62 > pdf.h - pdf.b_margin:
                pdf.add_page()
                row_y = pdf.get_y() + 2
        cell_x = pdf.l_margin + column * (width + gap)
        pdf.image(
            str(snapshots[point.event_id]), x=cell_x, y=row_y, w=width, h=48, keep_aspect_ratio=True
        )
        pdf.set_xy(cell_x, row_y + 49)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(width, 4, f"#{index}  {point.plate_text}  ({point.plate_confidence * 100:.0f}%)")
        pdf.set_xy(cell_x, row_y + 53)
        pdf.set_font("Helvetica", "", 7.5)
        when = f"{_ist(point.camera_time)} IST" if point.camera_time else TIME_UNKNOWN
        pdf.cell(width, 4, f"{point.camera_name[:30]}  |  {when}")
        if column == per_row - 1 or slot == len(hops) - 1:
            pdf.set_y(row_y + 60)


def _render_pdf(
    route: VehicleRoute,
    *,
    generated_at: datetime,
    snapshots: Mapping[str, Path] | None = None,
    basemap: Basemap | None = None,
) -> bytes:
    pdf = FPDF(orientation="landscape", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Sentinel Platform - Movement Report", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(
        0,
        6,
        f"Generated {_ist(generated_at)} IST ({generated_at.strftime(_HUMAN_TIME)} UTC)"
        "  |  sighting times are each camera's own burned-in clock, in IST (UTC+05:30); "
        "report.csv carries UTC too",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Plate: {route.plate_normalised}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"{route.total_sightings} sighting(s)"
        + (
            f"  |  first seen {_ist(route.first_seen_at)} IST"
            f"  |  last seen {_ist(route.last_seen_at)} IST"
            if route.first_seen_at and route.last_seen_at
            else ""
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    if not route.points and not route.untimed:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, "No sightings in the reconstructed window.", new_x="LMARGIN", new_y="NEXT")
        return bytes(pdf.output())

    sketch_y = pdf.get_y()
    _draw_route_sketch(
        pdf, route, x=pdf.l_margin, y=sketch_y, w=_MAP_W_MM, h=_MAP_H_MM, basemap=basemap
    )
    pdf.set_xy(pdf.l_margin, sketch_y + _MAP_H_MM + 1)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(90, 90, 90)
    where = (
        "Route on a street map captured at export, at each camera's coordinates"
        if basemap is not None
        else "Route drawn to scale from camera coordinates (no basemap)"
    )
    pdf.cell(
        0,
        5,
        f"{where}, sightings with a readable camera clock only. "
        "Solid: confirmed reads; dashed: probable - confirm on the evidence.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    headers = [
        "#",
        "Camera",
        "Location",
        "Camera clock (IST)",
        "Plate read",
        "Conf.",
        "Match",
        "Hop type",
    ]
    widths = [10, 55, 45, 48, 35, 18, 28, 28]

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    for header, width in zip(headers, widths, strict=True):
        pdf.cell(width, 8, header, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    for i, point in enumerate(route.points, start=1):
        location = f"{point.location.lat:.4f}, {point.location.lon:.4f}" if point.location else "-"
        row = [
            str(i),
            point.camera_name[:32],
            location,
            _camera_ist(point),
            point.plate_text,
            f"{point.plate_confidence * 100:.0f}%",
            point.match_rung,
            ("IMPOSSIBLE" if point.infeasible else "")
            or ("confirmed" if point.confirmed else "probable"),
        ]
        for value, width in zip(row, widths, strict=True):
            pdf.cell(width, 7, value, border=1)
        pdf.ln()

    if route.untimed:
        _render_untimed(pdf, route)
    if snapshots:
        _render_evidence(pdf, route, snapshots)
    return bytes(pdf.output())


def _render_untimed(pdf: FPDF, route: VehicleRoute) -> None:
    """Sightings whose camera clock could not be read: real, and listed, but
    not on the route — no other time may stand in for the camera's."""
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(
        0,
        7,
        f"Also seen - camera clock unreadable, time unknown ({len(route.untimed)})",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(
        0,
        5,
        "The camera's burned-in clock could not be read on these frames, so they are not "
        "placed on the route. Confirm each against its evidence frame.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    headers = ["#", "Camera", "Location", "Camera clock", "Plate read", "Conf.", "Match"]
    widths = [10, 55, 45, 76, 35, 18, 28]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    for header, width in zip(headers, widths, strict=True):
        pdf.cell(width, 8, header, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for i, point in enumerate(route.untimed, start=1):
        location = f"{point.location.lat:.4f}, {point.location.lon:.4f}" if point.location else "-"
        row = [
            f"U{i}",
            point.camera_name[:32],
            location,
            TIME_UNKNOWN,
            point.plate_text,
            f"{point.plate_confidence * 100:.0f}%",
            point.match_rung,
        ]
        for value, width in zip(row, widths, strict=True):
            pdf.cell(width, 7, value, border=1)
        pdf.ln()


def build_movement_report_zip(
    route: VehicleRoute,
    *,
    generated_by: str,
    snapshots: Mapping[str, Path] | None = None,
    basemap: Basemap | None = None,
) -> tuple[bytes, str]:
    """Returns (zip_bytes, filename). The zip contains report.pdf, report.csv,
    the face-blurred snapshot behind each hop (evidence/), and manifest.json —
    whose sha256 fields are computed over the exact bytes sitting next to it
    in the same archive. `snapshots` maps a hop's event_id to its file;
    `basemap` is the street map behind the route, when one could be fetched."""
    snapshots = snapshots or {}
    generated_at = datetime.now(UTC)
    pdf_bytes = _render_pdf(route, generated_at=generated_at, snapshots=snapshots, basemap=basemap)
    csv_bytes = _render_csv(route)
    evidence: dict[str, bytes] = {}
    named = [(f"hop-{i:02d}", p) for i, p in enumerate(route.points, start=1)]
    named += [(f"untimed-{i:02d}", p) for i, p in enumerate(route.untimed, start=1)]
    for label, point in named:
        path = snapshots.get(point.event_id)
        if path is not None:
            evidence[f"evidence/{label}-{point.event_id}.jpg"] = path.read_bytes()

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    # A chained hash over the two artifact hashes — the same "hash the hash"
    # tamper-evidence idea as the audit-log/evidence chain described in
    # docs/01-ARCHITECTURE.md section 6.5, scoped down to this one export.
    report_sha256 = hashlib.sha256(f"{pdf_sha256}:{csv_sha256}".encode()).hexdigest()

    manifest = {
        "plate_normalised": route.plate_normalised,
        "generated_at": generated_at.isoformat(),
        "generated_by": generated_by,
        "point_count": route.total_sightings,
        "untimed_count": len(route.untimed),
        "time_basis": "each camera's own burned-in clock; untimed sightings: unreadable",
        "first_seen_at": route.first_seen_at.isoformat() if route.first_seen_at else None,
        "last_seen_at": route.last_seen_at.isoformat() if route.last_seen_at else None,
        "files": {
            "report.pdf": {"sha256": pdf_sha256, "bytes": len(pdf_bytes)},
            "report.csv": {"sha256": csv_sha256, "bytes": len(csv_bytes)},
            **{
                name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                for name, data in evidence.items()
            },
        },
        "report_sha256": report_sha256,
        "note": (
            "report_sha256 = sha256(report.pdf sha256 + ':' + report.csv sha256). "
            "Recompute both file hashes and this value to verify neither artifact "
            "has been altered since export."
        ),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.pdf", pdf_bytes)
        archive.writestr("report.csv", csv_bytes)
        for name, data in evidence.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", _json_dumps(manifest))

    filename = (
        f"movement-report-{route.plate_normalised}-{generated_at.strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    return buffer.getvalue(), filename


def _json_dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
