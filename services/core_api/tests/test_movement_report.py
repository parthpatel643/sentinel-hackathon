"""Movement Report export tests — no DB required, this is pure rendering
over an in-memory VehicleRoute."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO

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
