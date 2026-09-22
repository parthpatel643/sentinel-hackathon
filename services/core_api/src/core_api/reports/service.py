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
import zipfile
from datetime import UTC, datetime

from fpdf import FPDF

from core_api.detections.schemas import VehicleRoute

__all__ = ["build_movement_report_zip"]

_CSV_HEADER = [
    "hop",
    "camera_id",
    "camera_name",
    "latitude",
    "longitude",
    "observed_at_utc",
    "plate_text",
    "plate_confidence",
    "match_rung",
    "confirmed",
    "snapshot_uri",
]


def _render_csv(route: VehicleRoute) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_HEADER)
    for i, point in enumerate(route.points, start=1):
        writer.writerow(
            [
                i,
                point.camera_id,
                point.camera_name,
                point.location.lat if point.location else "",
                point.location.lon if point.location else "",
                point.observed_at.isoformat(),
                point.plate_text,
                f"{point.plate_confidence:.3f}",
                point.match_rung,
                point.confirmed,
                point.snapshot_uri or "",
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _render_pdf(route: VehicleRoute, *, generated_at: datetime) -> bytes:
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
        f"Generated {generated_at.strftime('%d %b %Y, %H:%M:%S')} UTC",
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
            f"  |  first seen {route.first_seen_at.strftime('%d %b %Y, %H:%M:%S')} UTC"
            f"  |  last seen {route.last_seen_at.strftime('%d %b %Y, %H:%M:%S')} UTC"
            if route.first_seen_at and route.last_seen_at
            else ""
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    if not route.points:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, "No sightings in the reconstructed window.", new_x="LMARGIN", new_y="NEXT")
        return bytes(pdf.output())

    headers = [
        "#",
        "Camera",
        "Location",
        "Observed at (UTC)",
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
            point.observed_at.strftime("%d %b %Y, %H:%M:%S"),
            point.plate_text,
            f"{point.plate_confidence * 100:.0f}%",
            point.match_rung,
            "confirmed" if point.confirmed else "probable",
        ]
        for value, width in zip(row, widths, strict=True):
            pdf.cell(width, 7, value, border=1)
        pdf.ln()

    return bytes(pdf.output())


def build_movement_report_zip(route: VehicleRoute, *, generated_by: str) -> tuple[bytes, str]:
    """Returns (zip_bytes, filename). The zip contains report.pdf, report.csv
    and manifest.json — the manifest's sha256 fields are computed over the
    exact pdf/csv bytes sitting next to it in the same archive."""
    generated_at = datetime.now(UTC)
    pdf_bytes = _render_pdf(route, generated_at=generated_at)
    csv_bytes = _render_csv(route)

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
        "first_seen_at": route.first_seen_at.isoformat() if route.first_seen_at else None,
        "last_seen_at": route.last_seen_at.isoformat() if route.last_seen_at else None,
        "files": {
            "report.pdf": {"sha256": pdf_sha256, "bytes": len(pdf_bytes)},
            "report.csv": {"sha256": csv_sha256, "bytes": len(csv_bytes)},
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
        archive.writestr("manifest.json", _json_dumps(manifest))

    filename = (
        f"movement-report-{route.plate_normalised}-{generated_at.strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    return buffer.getvalue(), filename


def _json_dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
