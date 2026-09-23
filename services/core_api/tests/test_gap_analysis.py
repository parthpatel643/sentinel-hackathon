"""Coverage gap analysis — a real PostGIS ST_SquareGrid + ST_Distance query,
not a mocked geometry calculation."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Camera, Detection
from core_api.registry.gap_analysis import compute_coverage_gaps
from core_api.registry.schemas import GeoPointOut
from core_api.registry.service import upsert_camera


@pytest_asyncio.fixture(autouse=True)
async def _empty_camera_registry(db_session: AsyncSession) -> AsyncIterator[None]:
    """Coverage is a property of the whole fleet, so these tests reason about
    the entire `cameras` table — "no cameras", "one camera" — and therefore
    need to own it.

    They did, right up until the registry was pointed at a real catalogue and
    the dev database gained thirty live cameras; "no cameras yields an empty
    report" then failed on a grid of 1.5 million cells. Whether a test passes
    should not depend on what a developer happens to have onboarded, so give
    it the empty fleet it is describing. `db_session` rolls this back, so no
    real registry is harmed.
    """
    await db_session.execute(delete(Detection))
    await db_session.execute(delete(Camera))
    yield


async def test_no_cameras_yields_an_empty_report(db_session: AsyncSession) -> None:
    report = await compute_coverage_gaps(db_session)

    assert report.total_cells == 0
    assert report.cells == []


async def test_a_single_camera_covers_its_own_immediate_vicinity(db_session: AsyncSession) -> None:
    await upsert_camera(
        db_session,
        camera_id="gap-cam-01",
        name="Cam",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=23.0225, lon=72.5714),
        tier="a_continuous",
        status="live",
        source="manual",
        attributes={},
        profiles=[],
    )

    report = await compute_coverage_gaps(db_session, coverage_radius_m=2000.0, cell_size_m=500.0)

    assert report.total_cells > 0
    # The cell containing (or nearest to) the camera itself must be covered —
    # not every cell in the grid needs to be, but at least one must.
    assert report.covered_cells >= 1
    nearest_ids = {c.nearest_camera_id for c in report.cells}
    assert "gap-cam-01" in nearest_ids


async def test_a_far_away_camera_does_not_cover_a_distant_grid(db_session: AsyncSession) -> None:
    """With a small coverage radius relative to the grid's own margin, most
    cells must come back uncovered — proving this is a real distance
    threshold, not a rubber-stamped 'everything is fine'."""
    await upsert_camera(
        db_session,
        camera_id="gap-cam-02",
        name="Cam",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=23.0225, lon=72.5714),
        tier="a_continuous",
        status="live",
        source="manual",
        attributes={},
        profiles=[],
    )

    report = await compute_coverage_gaps(db_session, coverage_radius_m=10.0, cell_size_m=500.0)

    assert report.uncovered_cells > report.covered_cells


async def test_nearest_camera_distance_is_reported_for_every_cell(db_session: AsyncSession) -> None:
    await upsert_camera(
        db_session,
        camera_id="gap-cam-03",
        name="Cam",
        driver_id="rtsp",
        department_name=None,
        site_name=None,
        location=GeoPointOut(lat=23.0225, lon=72.5714),
        tier="a_continuous",
        status="live",
        source="manual",
        attributes={},
        profiles=[],
    )

    report = await compute_coverage_gaps(db_session, coverage_radius_m=500.0, cell_size_m=500.0)

    assert all(c.nearest_camera_distance_m is not None for c in report.cells)
    assert all(c.nearest_camera_distance_m >= 0 for c in report.cells)  # type: ignore[operator]
