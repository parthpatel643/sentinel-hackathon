"""Detection ingest and search — the read side of the ANPR pipeline.

`ingest_detection` is the one place a raw edge-worker POST becomes a
persisted, queryable fact; it is also where watchlist correlation attaches
(see core_api/watchlist/correlator.py), so a detection and "did this trigger
an alert" are always decided together, not in two places that can drift.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Camera, Detection
from core_api.detections.schemas import DetectionIn, DetectionOut, RoutePoint, VehicleRoute
from core_api.registry.service import location_out
from sentinel_core.plates import ambiguity_key, normalise_plate

__all__ = ["get_vehicle_route", "ingest_detection", "search_detections"]


async def ingest_detection(session: AsyncSession, payload: DetectionIn) -> Detection:
    detection = Detection(
        event_id=payload.event_id,
        camera_id=payload.camera_id,
        plate_text=payload.plate_text,
        plate_normalised=payload.plate_normalised,
        plate_ambiguity_key=payload.plate_ambiguity_key,
        plate_confidence=payload.plate_confidence,
        format_valid=payload.format_valid,
        frames_voted=payload.frames_voted,
        vehicle_class=payload.vehicle_class,
        vehicle_track_id=payload.vehicle_track_id,
        bbox_x=payload.bbox.x if payload.bbox else None,
        bbox_y=payload.bbox.y if payload.bbox else None,
        bbox_width=payload.bbox.width if payload.bbox else None,
        bbox_height=payload.bbox.height if payload.bbox else None,
        pts_ms=payload.pts_ms,
        observed_at=payload.observed_at,
        snapshot_uri=payload.snapshot_uri,
        node_id=payload.node_id,
        model_versions=payload.model_versions,
    )
    session.add(detection)

    # A detection is itself proof of life for the camera that produced it —
    # opportunistically mark it live even between explicit health heartbeats.
    await session.execute(
        update(Camera)
        .where(Camera.camera_id == payload.camera_id)
        .values(status="live", last_seen_at=payload.observed_at)
    )

    await session.flush()
    return detection


async def search_detections(
    session: AsyncSession,
    *,
    plate: str | None = None,
    camera_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
) -> list[DetectionOut]:
    query = select(Detection)
    if plate:
        query = query.where(Detection.plate_normalised == normalise_plate(plate))
    if camera_id:
        query = query.where(Detection.camera_id == camera_id)
    if since:
        query = query.where(Detection.observed_at >= since)
    if until:
        query = query.where(Detection.observed_at <= until)

    result = await session.execute(query.order_by(Detection.observed_at.desc()).limit(limit))
    return [DetectionOut.model_validate(d) for d in result.scalars().all()]


async def get_vehicle_route(
    session: AsyncSession, plate_query: str, *, window: timedelta = timedelta(hours=24)
) -> VehicleRoute:
    """Reconstruct a vehicle's route: exact match first, falling back to an
    OCR-ambiguity-class match if nothing exact is found — rungs 1-2 of the
    matching ladder in docs/01-ARCHITECTURE.md section 6.1. Edit-distance and
    partial/wildcard (rungs 3-4) are a documented next step.
    """
    normalised = normalise_plate(plate_query)
    since = datetime.now(UTC) - window

    exact_query = (
        select(Detection, Camera)
        .join(Camera, Camera.camera_id == Detection.camera_id)
        .where(Detection.plate_normalised == normalised, Detection.observed_at >= since)
        .order_by(Detection.observed_at.asc())
    )
    rows = (await session.execute(exact_query)).all()
    match_rung = "exact"

    if not rows:
        ambiguity = ambiguity_key(plate_query)
        fallback_query = (
            select(Detection, Camera)
            .join(Camera, Camera.camera_id == Detection.camera_id)
            .where(Detection.plate_ambiguity_key == ambiguity, Detection.observed_at >= since)
            .order_by(Detection.observed_at.asc())
        )
        rows = (await session.execute(fallback_query)).all()
        match_rung = "ambiguity_class"

    points = [
        RoutePoint(
            camera_id=camera.camera_id,
            camera_name=camera.name,
            location=location_out(camera.location),
            observed_at=detection.observed_at,
            plate_text=detection.plate_text,
            plate_confidence=detection.plate_confidence,
            match_rung=match_rung,
            snapshot_uri=detection.snapshot_uri,
            confirmed=True,
        )
        for detection, camera in rows
    ]

    return VehicleRoute(
        plate_normalised=normalised,
        total_sightings=len(points),
        first_seen_at=points[0].observed_at if points else None,
        last_seen_at=points[-1].observed_at if points else None,
        points=points,
    )
