"""Detection ingest and search — the read side of the ANPR pipeline.

`ingest_detection` is the one place a raw edge-worker POST becomes a
persisted, queryable fact; it is also where watchlist correlation attaches
(see core_api/watchlist/correlator.py), so a detection and "did this trigger
an alert" are always decided together, not in two places that can drift.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from sqlalchemy import Row, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Camera, Detection
from core_api.detections.schemas import DetectionIn, DetectionOut, RoutePoint, VehicleRoute
from core_api.registry.service import location_out
from sentinel_core.plates import ambiguity_key, normalise_plate

__all__ = [
    "detection_exists",
    "get_vehicle_route",
    "ingest_detection",
    "search_detections",
    "within_one_edit",
]

# Rung 3 only engages for plate-length queries: a short fragment is one edit
# away from far too many real plates for the result to mean anything.
EDIT_DISTANCE_MIN_LENGTH = 7
EDIT_DISTANCE_MAX_CANDIDATES = 5


def within_one_edit(a: str, b: str) -> bool:
    """True when `a` and `b` differ by at most one substitution, insertion
    or deletion — an OCR read that dropped, added or misread one character
    outside the ambiguity classes (which rung 2 already covers)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


async def detection_exists(session: AsyncSession, event_id: str, observed_at: datetime) -> bool:
    found = await session.scalar(
        select(Detection.id).where(
            Detection.event_id == event_id, Detection.observed_at == observed_at
        )
    )
    return found is not None


async def ingest_detection(session: AsyncSession, payload: DetectionIn) -> Detection:
    # Search and watchlist matching key on these two columns, so they are
    # derived here from the plate text rather than trusted from the producer:
    # a third-party ANPR feed sending "GJ 01 AB 1234" as its normalised form
    # would otherwise be unfindable under the plate an operator types.
    detection = Detection(
        event_id=payload.event_id,
        camera_id=payload.camera_id,
        plate_text=payload.plate_text,
        plate_normalised=normalise_plate(payload.plate_text),
        plate_ambiguity_key=ambiguity_key(payload.plate_text),
        plate_confidence=payload.plate_confidence,
        format_valid=payload.format_valid,
        frames_voted=payload.frames_voted,
        vehicle_class=payload.vehicle_class,
        vehicle_colour=payload.vehicle_colour,
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
        # Our receipt time, not the frame's: observed_at is the scene's own
        # clock, which on replayed or mis-set cameras is days or months old
        # and would make a working camera look stale.
        .values(status="live", last_seen_at=datetime.now(UTC))
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
    """Reconstruct a vehicle's route down the matching ladder in
    docs/01-ARCHITECTURE.md section 6.1, stopping at the first rung that
    finds anything: exact, then OCR-ambiguity class, then reads exactly one
    character away (rung 3). Rung-3 hops are returned `confirmed=False` —
    they may be a different vehicle whose plate differs by one character, so
    the console draws them as probable and the operator confirms each
    against its snapshot. Partial/wildcard (rung 4) is a documented next step.
    """
    normalised = normalise_plate(plate_query)
    since = datetime.now(UTC) - window

    # The window is bounded by when *we* recorded the sighting, not by the
    # timestamp burned into the frame. Those are different clocks and only
    # one of them is ours: `observed_at` is the scene's own time, which is
    # what belongs in evidence, but it is only as trustworthy as the camera
    # that produced it. A camera with a mis-set clock — routine in a large
    # estate, and the reason time sync matters here at all — would otherwise
    # drop out of "seen in the last 24 hours" entirely, making a vehicle
    # unfindable precisely because one camera was wrong. Ordering stays on
    # `observed_at`: a route is a journey through the scene, so it must be
    # told in the scene's order.
    exact_query = (
        select(Detection, Camera)
        .join(Camera, Camera.camera_id == Detection.camera_id)
        .where(Detection.plate_normalised == normalised, Detection.created_at >= since)
        .order_by(Detection.observed_at.asc())
    )
    rows = (await session.execute(exact_query)).all()
    match_rung = "exact"

    if not rows:
        ambiguity = ambiguity_key(plate_query)
        fallback_query = (
            select(Detection, Camera)
            .join(Camera, Camera.camera_id == Detection.camera_id)
            .where(Detection.plate_ambiguity_key == ambiguity, Detection.created_at >= since)
            .order_by(Detection.observed_at.asc())
        )
        rows = (await session.execute(fallback_query)).all()
        match_rung = "ambiguity_class"

    if not rows and len(normalised) >= EDIT_DISTANCE_MIN_LENGTH:
        seen_plates = (
            await session.execute(
                select(Detection.plate_normalised)
                .where(Detection.created_at >= since)
                .group_by(Detection.plate_normalised)
                .order_by(func.count().desc())
            )
        ).scalars()
        near = [p for p in seen_plates if within_one_edit(p, normalised)]
        if near:
            near_query = (
                select(Detection, Camera)
                .join(Camera, Camera.camera_id == Detection.camera_id)
                .where(
                    Detection.plate_normalised.in_(near[:EDIT_DISTANCE_MAX_CANDIDATES]),
                    Detection.created_at >= since,
                )
                .order_by(Detection.observed_at.asc())
            )
            rows = (await session.execute(near_query)).all()
            match_rung = "edit_distance"

    points = [
        _route_point(detection, camera, match_rung, confirmed=match_rung != "edit_distance")
        for detection, camera in rows
    ]
    if match_rung in ("exact", "ambiguity_class"):
        points = await _bridge_unread_hops(session, normalised, rows, points, since=since)
    _mark_feasibility(points)

    return VehicleRoute(
        plate_normalised=normalised,
        total_sightings=len(points),
        first_seen_at=points[0].observed_at if points else None,
        last_seen_at=points[-1].observed_at if points else None,
        points=points,
    )


def _route_point(
    detection: Detection, camera: Camera, match_rung: str, *, confirmed: bool
) -> RoutePoint:
    return RoutePoint(
        event_id=detection.event_id,
        camera_id=camera.camera_id,
        camera_name=camera.name,
        location=location_out(camera.location),
        observed_at=detection.observed_at,
        plate_text=detection.plate_text,
        plate_confidence=detection.plate_confidence,
        match_rung=match_rung,
        snapshot_uri=detection.snapshot_uri,
        confirmed=confirmed,
    )


# Above this, two consecutive sightings cannot be one vehicle on a road: the
# plate is cloned, a camera clock is wrong, or one of the reads is not it.
INFEASIBLE_SPEED_KMH = 150.0
# Bridged hops must be comfortably reachable, not merely possible.
BRIDGE_MAX_SPEED_KMH = 120.0
BRIDGE_TAIL_CHARS = 4
BRIDGE_MAX_EDITS = 3


def _edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _km_between(a: RoutePoint, b: RoutePoint) -> float | None:
    if a.location is None or b.location is None:
        return None
    lat1, lon1, lat2, lon2 = map(
        math.radians, (a.location.lat, a.location.lon, b.location.lat, b.location.lon)
    )
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _speed_kmh(a: RoutePoint, b: RoutePoint) -> float | None:
    km = _km_between(a, b)
    if km is None:
        return None
    hours = (b.observed_at - a.observed_at).total_seconds() / 3600
    if km < 0.05:
        return 0.0
    return math.inf if hours <= 0 else km / hours


def _mark_feasibility(points: list[RoutePoint]) -> None:
    """Stamps each hop with the speed implied from the hop before it, and
    flags travel no vehicle could make."""
    for previous, point in pairwise(points):
        speed = _speed_kmh(previous, point)
        if speed is None:
            continue
        point.implied_speed_kmh = None if math.isinf(speed) else round(speed, 1)
        point.infeasible = speed > INFEASIBLE_SPEED_KMH


async def _bridge_unread_hops(
    session: AsyncSession,
    normalised: str,
    rows: Sequence[Row[tuple[Detection, Camera]]],
    points: list[RoutePoint],
    *,
    since: datetime,
) -> list[RoutePoint]:
    """Rungs 4-5 of the matching ladder, conservatively: a read whose plate
    shares the target's last four characters and is at most three edits
    away, made by a vehicle of the same class and colour as every confirmed
    sighting, and reachable at road speed from the confirmed hops either side
    of it. Returned as probable — an operator confirms each on its frame."""
    classes = {d.vehicle_class for d, _ in rows}
    colours = {d.vehicle_colour for d, _ in rows}
    if len(classes) != 1 or len(colours) != 1 or None in classes or None in colours:
        return points  # no consistent appearance to bridge on
    vehicle_class, colour = classes.pop(), colours.pop()
    tail = normalised[-BRIDGE_TAIL_CHARS:]
    known = {d.event_id for d, _ in rows}
    candidates = (
        await session.execute(
            select(Detection, Camera)
            .join(Camera, Camera.camera_id == Detection.camera_id)
            .where(
                Detection.created_at >= since,
                Detection.plate_normalised.like(f"%{tail}"),
                Detection.plate_normalised != normalised,
                Detection.vehicle_class == vehicle_class,
                Detection.vehicle_colour == colour,
            )
        )
    ).all()
    bridged = list(points)
    for detection, camera in candidates:
        if detection.event_id in known:
            continue
        if _edit_distance(detection.plate_normalised, normalised) > BRIDGE_MAX_EDITS:
            continue
        candidate = _route_point(detection, camera, "partial_attribute", confirmed=False)
        before = [p for p in points if p.observed_at <= candidate.observed_at]
        after = [p for p in points if p.observed_at > candidate.observed_at]
        neighbours = ([before[-1]] if before else []) + ([after[0]] if after else [])
        speeds = [
            _speed_kmh(*sorted((n, candidate), key=lambda p: p.observed_at)) for n in neighbours
        ]
        if neighbours and all(s is not None and s <= BRIDGE_MAX_SPEED_KMH for s in speeds):
            bridged.append(candidate)
    bridged.sort(key=lambda p: (p.observed_at, p.event_id))
    return bridged
