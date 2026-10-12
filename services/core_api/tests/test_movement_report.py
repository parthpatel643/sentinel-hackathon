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

import httpx
from PIL import Image
from pypdf import PdfReader

from core_api.detections.schemas import RoutePoint, VehicleRoute
from core_api.registry.schemas import GeoPointOut
from core_api.reports.basemap import fetch_basemap, plan_view, world_pixel
from core_api.reports.service import MAP_ASPECT, build_movement_report_zip
from sentinel_core.config import Settings

# When the footage was processed — never the time a report shows.
PROCESSED_AT = datetime(2026, 10, 10, 6, 0, 0, tzinfo=UTC)


def _sample_route() -> VehicleRoute:
    points = [
        RoutePoint(
            camera_id="cam-01",
            camera_name="Sarkhej Circle",
            location=GeoPointOut(lat=23.0225, lon=72.5714),
            camera_time=datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC),
            observed_at=PROCESSED_AT,
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
            camera_time=datetime(2026, 9, 22, 10, 12, 0, tzinfo=UTC),
            observed_at=PROCESSED_AT,
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
        first_seen_at=points[0].camera_time,
        last_seen_at=points[-1].camera_time,
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


def test_csv_carries_the_camera_clock_in_utc_and_ist_for_every_hop() -> None:
    zip_bytes, _ = build_movement_report_zip(_sample_route(), generated_by="test@example.com")

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        csv_text = archive.read("report.csv").decode()
        rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert rows[0]["camera_clock"] == "read"
    assert rows[0]["camera_time_utc"] == "2026-09-22T10:00:00+00:00"
    assert rows[0]["camera_time_ist"] == "2026-09-22T15:30:00+05:30"
    for row in rows:
        utc = datetime.fromisoformat(row["camera_time_utc"])
        assert datetime.fromisoformat(row["camera_time_ist"]) == utc
    assert "2026-10-10" not in csv_text, "processing time must never appear in a report"


def _route_with_an_untimed_sighting() -> VehicleRoute:
    route = _sample_route()
    untimed = route.points[1].model_copy(
        update={
            "event_id": "01JREPORTUNTIMED000000001",
            "camera_id": "cam-09",
            "camera_name": "Janpath",
            "camera_time": None,
        }
    )
    return route.model_copy(update={"untimed": [untimed], "total_sightings": 3})


def test_a_sighting_with_an_unreadable_clock_is_listed_as_time_unknown(tmp_path: Path) -> None:
    """It is a real sighting, so the report includes it — labelled, off the
    route, with its evidence frame, and with no other time in its place."""
    route = _route_with_an_untimed_sighting()
    snapshots = {"01JREPORTUNTIMED000000001": _jpeg(tmp_path / "u.jpg", 90)}

    zip_bytes, _ = build_movement_report_zip(
        route, generated_by="test@example.com", snapshots=snapshots
    )

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("report.csv").decode())))
        manifest = json.loads(archive.read("manifest.json"))
        names = archive.namelist()
        text = "\n".join(
            page.extract_text() for page in PdfReader(BytesIO(archive.read("report.pdf"))).pages
        )

    untimed = [r for r in rows if r["camera_clock"] == "unreadable"]
    assert [(r["hop"], r["camera_id"]) for r in untimed] == [("U1", "cam-09")]
    assert untimed[0]["camera_time_utc"] == untimed[0]["camera_time_ist"] == ""
    assert manifest["untimed_count"] == 1
    assert manifest["point_count"] == 3
    assert "evidence/untimed-01-01JREPORTUNTIMED000000001.jpg" in names
    assert "camera clock unreadable" in text
    assert "2026-10-10" not in text


def test_the_pdf_reports_sighting_times_by_the_cameras_clock() -> None:
    zip_bytes, _ = build_movement_report_zip(_sample_route(), generated_by="test@example.com")

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        text = PdfReader(BytesIO(archive.read("report.pdf"))).pages[0].extract_text()

    assert "Camera clock (IST)" in text
    assert "22 Sep 2026, 15:30:00" in text
    assert "10 Oct 2026, 11:30:00" not in text, "processing time must never appear"


def _route_with_events() -> VehicleRoute:
    route = _sample_route()
    third = route.points[1].model_copy(
        update={
            "camera_id": "cam-03",
            "camera_name": "Paldi",
            "location": GeoPointOut(lat=23.0105, lon=72.5640),
            "camera_time": datetime(2026, 9, 22, 10, 30, 0, tzinfo=UTC),
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


# --- the street map behind the route -----------------------------------------


def _tile_png() -> bytes:
    out = BytesIO()
    Image.new("RGB", (256, 256), (220, 230, 210)).save(out, format="PNG")
    return out.getvalue()


def _settings(tmp_path: Path, url: str = "https://tiles.test/{z}/{x}/{y}.png") -> Settings:
    return Settings(report_tile_url=url, report_tile_cache_dir=str(tmp_path / "tiles"))


def _locations(route: VehicleRoute) -> list[GeoPointOut]:
    return [p.location for p in route.points if p.location is not None]


def test_plan_view_fits_every_camera_inside_the_frame() -> None:
    points = _locations(_route_with_events())
    zoom, left, top = plan_view(points, 1200, 381)
    for p in points:
        x, y = world_pixel(p.lat, p.lon, zoom)
        assert 0 < x - left < 1200 and 0 < y - top < 381
    # One zoom closer would no longer fit.
    xs = [world_pixel(p.lat, p.lon, zoom + 1)[0] for p in points]
    ys = [world_pixel(p.lat, p.lon, zoom + 1)[1] for p in points]
    assert max(xs) - min(xs) > 1200 * 0.76 or max(ys) - min(ys) > 381 * 0.76


async def test_basemap_is_stitched_from_tiles_and_cached(tmp_path: Path) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        assert request.headers["user-agent"].startswith("Sentinel-Platform")
        return httpx.Response(200, content=_tile_png())

    points = _locations(_route_with_events())
    settings = _settings(tmp_path)
    basemap = await fetch_basemap(
        points, aspect=MAP_ASPECT, settings=settings, transport=httpx.MockTransport(handler)
    )

    assert basemap is not None
    assert Image.open(BytesIO(basemap.image_png)).size == (basemap.width_px, basemap.height_px)
    for p in points:
        fx, fy = basemap.place(p.lat, p.lon)
        assert 0 < fx < 1 and 0 < fy < 1
    fetched = len(requested)
    assert fetched > 0

    # The same area again comes from the disk cache.
    again = await fetch_basemap(
        points, aspect=MAP_ASPECT, settings=settings, transport=httpx.MockTransport(handler)
    )
    assert again is not None and len(requested) == fetched


async def test_no_basemap_when_tiles_are_unreachable_or_disabled(tmp_path: Path) -> None:
    points = _locations(_route_with_events())
    failing = httpx.MockTransport(lambda request: httpx.Response(503))
    not_a_tile = httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html>"))

    for transport in (failing, not_a_tile):
        assert (
            await fetch_basemap(
                points, aspect=MAP_ASPECT, settings=_settings(tmp_path), transport=transport
            )
            is None
        )
    assert await fetch_basemap(points, aspect=MAP_ASPECT, settings=_settings(tmp_path, "")) is None


async def test_report_draws_the_route_over_the_fetched_map(tmp_path: Path) -> None:
    route = _route_with_events()
    basemap = await fetch_basemap(
        _locations(route),
        aspect=MAP_ASPECT,
        settings=_settings(tmp_path),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=_tile_png())),
    )

    zip_bytes, _ = build_movement_report_zip(route, generated_by="t@example.com", basemap=basemap)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        page = PdfReader(BytesIO(archive.read("report.pdf"))).pages[0]
    text = page.extract_text()
    assert "street map captured at export" in text
    assert "OpenStreetMap contributors" in text
    assert "km" in text
    assert len(page.images) == 1
