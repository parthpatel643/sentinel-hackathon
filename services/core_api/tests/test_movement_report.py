"""Movement Report export tests — no DB required, this is pure rendering
over an in-memory VehicleRoute."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from core_api.detections.schemas import RoutePoint, VehicleRoute
from core_api.registry.schemas import GeoPointOut
from core_api.reports.service import build_movement_report_zip


def _sample_route() -> VehicleRoute:
    points = [
        RoutePoint(
            camera_id="cam-01",
            camera_name="Sarkhej Circle",
            location=GeoPointOut(lat=23.0225, lon=72.5714),
            observed_at=datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC),
            plate_text="GJ01AB1234",
            plate_confidence=0.94,
            match_rung="exact",
            snapshot_uri=None,
            confirmed=True,
        ),
        RoutePoint(
            camera_id="cam-02",
            camera_name="Ellisbridge",
            location=GeoPointOut(lat=23.0289, lon=72.5589),
            observed_at=datetime(2026, 9, 22, 10, 12, 0, tzinfo=UTC),
            plate_text="GJ01AB1234",
            plate_confidence=0.88,
            match_rung="exact",
            snapshot_uri="s3://evidence/cam-02/1.jpg",
            confirmed=True,
        ),
    ]
    return VehicleRoute(
        plate_normalised="GJ01AB1234",
        total_sightings=len(points),
        first_seen_at=points[0].observed_at,
        last_seen_at=points[-1].observed_at,
        points=points,
    )


def test_zip_contains_pdf_csv_and_manifest() -> None:
    zip_bytes, filename = build_movement_report_zip(
        _sample_route(), generated_by="admin@sentinel-platform.com"
    )

    assert filename.startswith("movement-report-GJ01AB1234-")
    assert filename.endswith(".zip")

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        assert set(archive.namelist()) == {"report.pdf", "report.csv", "manifest.json"}
        pdf_bytes = archive.read("report.pdf")
        csv_bytes = archive.read("report.csv")
        manifest = json.loads(archive.read("manifest.json"))

    assert pdf_bytes.startswith(b"%PDF")
    assert b"GJ01AB1234" in csv_bytes
    assert manifest["plate_normalised"] == "GJ01AB1234"
    assert manifest["generated_by"] == "admin@sentinel-platform.com"
    assert manifest["point_count"] == 2


def test_manifest_hashes_match_the_actual_artifact_bytes() -> None:
    """The whole point of the manifest is tamper evidence — the hashes it
    carries must be exactly recomputable from the bytes shipped alongside
    it, or a jury verifying the export would be trusting an unverifiable
    claim instead of checking one."""
    zip_bytes, _ = build_movement_report_zip(
        _sample_route(), generated_by="admin@sentinel-platform.com"
    )

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        pdf_bytes = archive.read("report.pdf")
        csv_bytes = archive.read("report.csv")
        manifest = json.loads(archive.read("manifest.json"))

    assert manifest["files"]["report.pdf"]["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert manifest["files"]["report.csv"]["sha256"] == hashlib.sha256(csv_bytes).hexdigest()

    expected_report_hash = hashlib.sha256(
        f"{manifest['files']['report.pdf']['sha256']}:{manifest['files']['report.csv']['sha256']}".encode()
    ).hexdigest()
    assert manifest["report_sha256"] == expected_report_hash


def test_empty_route_still_produces_a_valid_pdf() -> None:
    empty_route = VehicleRoute(
        plate_normalised="GJ05XY9999",
        total_sightings=0,
        first_seen_at=None,
        last_seen_at=None,
        points=[],
    )
    zip_bytes, _ = build_movement_report_zip(
        empty_route, generated_by="admin@sentinel-platform.com"
    )

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        pdf_bytes = archive.read("report.pdf")
        manifest = json.loads(archive.read("manifest.json"))

    assert pdf_bytes.startswith(b"%PDF")
    assert manifest["point_count"] == 0


def test_csv_carries_both_utc_and_ist_for_every_hop() -> None:
    zip_bytes, _ = build_movement_report_zip(_sample_route(), generated_by="test@example.com")

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("report.csv").decode())))

    assert rows[0]["observed_at_utc"] == "2026-09-22T10:00:00+00:00"
    assert rows[0]["observed_at_ist"] == "2026-09-22T15:30:00+05:30"
    for row in rows:
        utc = datetime.fromisoformat(row["observed_at_utc"])
        assert datetime.fromisoformat(row["observed_at_ist"]) == utc


def _route_with_events() -> VehicleRoute:
    route = _sample_route()
    third = route.points[1].model_copy(
        update={
            "camera_id": "cam-03",
            "camera_name": "Paldi",
            "location": GeoPointOut(lat=23.0105, lon=72.5640),
            "observed_at": datetime(2026, 9, 22, 10, 30, 0, tzinfo=UTC),
            "match_rung": "edit_distance",
            "confirmed": False,
        }
    )
    points = [
        p.model_copy(update={"event_id": f"01JREPORT{i:016d}"})
        for i, p in enumerate([*route.points, third])
    ]
    return route.model_copy(update={"points": points, "total_sightings": len(points)})


def _jpeg(path: Path, shade: int) -> Path:
    Image.new("RGB", (640, 360), (shade, shade, 200)).save(path, format="JPEG")
    return path


def test_report_carries_a_route_sketch_and_the_evidence_behind_each_hop(tmp_path: Path) -> None:
    route = _route_with_events()
    snapshots = {
        p.event_id: _jpeg(tmp_path / f"{p.event_id}.jpg", 40 * i)
        for i, p in enumerate(route.points)
    }

    zip_bytes, _ = build_movement_report_zip(
        route, generated_by="test@example.com", snapshots=snapshots
    )

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        names = sorted(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        pdf = PdfReader(BytesIO(archive.read("report.pdf")))
        evidence = {n: archive.read(n) for n in names if n.startswith("evidence/")}

    assert len(evidence) == 3
    assert "evidence/hop-03-01JREPORT0000000000000002.jpg" in evidence
    for name, data in evidence.items():
        assert manifest["files"][name]["sha256"] == hashlib.sha256(data).hexdigest()
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "drawn to scale" in text
    assert "Evidence - one frame per sighting" in text
    assert "km" in text and "N" in text
    assert sum(len(page.images) for page in pdf.pages) == 3


def test_report_without_snapshots_still_has_a_sketch_and_no_evidence(tmp_path: Path) -> None:
    zip_bytes, _ = build_movement_report_zip(_route_with_events(), generated_by="t@example.com")

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        assert not [n for n in archive.namelist() if n.startswith("evidence/")]
        text = PdfReader(BytesIO(archive.read("report.pdf"))).pages[0].extract_text()
    assert "drawn to scale" in text
