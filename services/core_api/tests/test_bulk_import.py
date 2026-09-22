"""Bulk CSV import: row-level validation is pure and unit-tested without a
database; the actual insert path needs the real Postgres."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.registry.bulk_import import parse_and_import_csv
from core_api.registry.service import list_cameras

MINIMAL_CSV = "camera_id,name\ncam-min-01,Minimal Camera\n"

FULL_CSV = (
    "camera_id,name,department_name,site_name,lat,lon,protocol,url,codec,width,height,declared_fps\n"
    "cam-full-01,Full Camera,GSRTC,Depot A,23.03,72.58,rtsp,rtsp://x/full01,h264,1920,1080,25\n"
)

MIXED_CSV = (
    "camera_id,name\n"
    "cam-mix-01,Good Row\n"
    ",Missing Id\n"  # camera_id blank
    "cam-mix-02,Also Good\n"
)

MISSING_COLUMN_CSV = "camera_id\ncam-x,\n"  # no 'name' column at all


async def test_dry_run_validates_without_writing_anything(db_session: AsyncSession) -> None:
    result = await parse_and_import_csv(db_session, MINIMAL_CSV, dry_run=True)

    assert result.dry_run is True
    assert result.succeeded == 1
    assert result.failed == 0

    cameras = await list_cameras(db_session)
    assert "cam-min-01" not in {c.camera_id for c in cameras}


async def test_commit_actually_persists_the_camera(db_session: AsyncSession) -> None:
    result = await parse_and_import_csv(db_session, MINIMAL_CSV, dry_run=False)

    assert result.succeeded == 1
    cameras = await list_cameras(db_session)
    assert "cam-min-01" in {c.camera_id for c in cameras}


async def test_a_full_row_creates_department_site_and_stream_profile(
    db_session: AsyncSession,
) -> None:
    await parse_and_import_csv(db_session, FULL_CSV, dry_run=False)

    cameras = await list_cameras(db_session)
    camera = next(c for c in cameras if c.camera_id == "cam-full-01")
    assert camera.department is not None
    assert camera.department.name == "GSRTC"
    assert camera.site is not None
    assert camera.site.name == "Depot A"
    assert len(camera.profiles) == 1
    assert camera.profiles[0].codec == "h264"


async def test_one_bad_row_does_not_block_the_good_ones(db_session: AsyncSession) -> None:
    result = await parse_and_import_csv(db_session, MIXED_CSV, dry_run=False)

    assert result.total_rows == 3
    assert result.succeeded == 2
    assert result.failed == 1

    cameras = await list_cameras(db_session)
    ids = {c.camera_id for c in cameras}
    assert "cam-mix-01" in ids
    assert "cam-mix-02" in ids


async def test_a_csv_missing_a_required_column_fails_cleanly(db_session: AsyncSession) -> None:
    result = await parse_and_import_csv(db_session, MISSING_COLUMN_CSV, dry_run=True)

    assert result.succeeded == 0
    assert result.failed == 1
    assert "name" in result.rows[0].error  # type: ignore[operator]
