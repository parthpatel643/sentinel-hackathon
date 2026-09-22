"""Catalogue-driven batch onboarding (upsert_from_descriptors) — the exact
path scripts/verify_gov_catalogue.py and the /cameras/discover endpoint use.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core_api.registry.service import list_cameras, upsert_from_descriptors
from sentinel_core.schemas import (
    AnalyticsTier,
    CameraDescriptor,
    CameraStatus,
    GeoPoint,
    StreamProfile,
    StreamProtocol,
)


def _descriptor(
    camera_id: str, *, tier: AnalyticsTier = AnalyticsTier.B_SAMPLED
) -> CameraDescriptor:
    return CameraDescriptor(
        camera_id=camera_id,
        name=f"Camera {camera_id}",
        driver_id="rtsp",
        department="Home Department",
        location=GeoPoint(lat=23.02, lon=72.57),
        profiles=[StreamProfile(protocol=StreamProtocol.RTSP, url=f"rtsp://x/{camera_id}")],
        tier=tier,
        status=CameraStatus.LIVE,
    )


async def test_a_batch_of_new_cameras_are_all_onboarded(db_session: AsyncSession) -> None:
    descriptors = [_descriptor(f"batch-{i:02d}") for i in range(5)]

    summary = await upsert_from_descriptors(db_session, descriptors, source="gov_catalogue")

    assert sorted(summary.onboarded) == [f"batch-{i:02d}" for i in range(5)]
    assert summary.updated == []
    assert summary.failed == []


async def test_re_running_the_same_batch_updates_instead_of_duplicating(
    db_session: AsyncSession,
) -> None:
    descriptors = [_descriptor("recon-01")]

    await upsert_from_descriptors(db_session, descriptors, source="gov_catalogue")
    second = await upsert_from_descriptors(db_session, descriptors, source="gov_catalogue")

    assert second.onboarded == []
    assert second.updated == ["recon-01"]
    cameras = await list_cameras(db_session)
    assert len([c for c in cameras if c.camera_id == "recon-01"]) == 1


async def test_a_duplicate_id_within_one_batch_is_treated_as_an_update(
    db_session: AsyncSession,
) -> None:
    """A buggy upstream catalogue that lists the same camera_id twice in one
    fetch must not take down the whole onboarding run. Because
    upsert_camera flushes on every call, the second occurrence finds the
    first one already persisted and correctly takes the update path rather
    than conflicting — which is the better outcome than a bare failure."""
    descriptors = [
        _descriptor("good-01"),
        _descriptor("dup-01"),
        _descriptor("dup-01"),  # deliberately repeated within this one batch
        _descriptor("good-02"),
    ]

    summary = await upsert_from_descriptors(db_session, descriptors, source="gov_catalogue")

    assert "good-01" in summary.onboarded
    assert "good-02" in summary.onboarded
    assert summary.failed == []
    # First occurrence onboards it; the second occurrence in the same batch
    # sees it already exists and updates instead of erroring or duplicating.
    assert summary.onboarded.count("dup-01") == 1
    assert summary.updated.count("dup-01") == 1
    cameras = await list_cameras(db_session)
    assert len([c for c in cameras if c.camera_id == "dup-01"]) == 1


async def test_tier_and_status_from_the_catalogue_are_persisted(db_session: AsyncSession) -> None:
    descriptors = [_descriptor("tiered-01", tier=AnalyticsTier.A_CONTINUOUS)]

    await upsert_from_descriptors(db_session, descriptors, source="gov_catalogue")

    cameras = await list_cameras(db_session)
    camera = next(c for c in cameras if c.camera_id == "tiered-01")
    assert camera.tier == "a_continuous"
    assert camera.status == "live"
    assert camera.source == "gov_catalogue"
