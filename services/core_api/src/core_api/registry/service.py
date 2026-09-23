"""Registry business logic: upsert, catalogue-driven onboarding, lookups.

Every write path — manual entry, bulk CSV, catalogue reconciliation — goes
through `upsert_camera` / `upsert_from_descriptors`, so there is exactly one
place that decides what "the same camera seen again" means (an upsert on
`camera_id`), not one behaviour per onboarding route.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from geoalchemy2.shape import to_shape
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core_api.db.models import Camera, Department, Site, StreamProfile
from core_api.registry.schemas import (
    CameraHealthUpdate,
    CameraOut,
    CameraStreamOut,
    DepartmentOut,
    GeoPointOut,
    StreamProfileIn,
    StreamProfileOut,
)
from sentinel_core.config import Settings
from sentinel_core.schemas import CameraDescriptor

__all__ = [
    "UpsertSummary",
    "camera_to_out",
    "department_to_out",
    "get_camera",
    "get_or_create_department",
    "get_or_create_site",
    "list_cameras",
    "list_departments",
    "location_out",
    "resolve_camera_stream",
    "upsert_camera",
    "upsert_from_descriptors",
]

logger = logging.getLogger(__name__)


def _point_wkt(lat: float, lon: float) -> str:
    """GeoAlchemy2 accepts an EWKT string directly as a column value —
    simpler than building an ST_GeomFromText() clause by hand."""
    return f"SRID=4326;POINT({lon} {lat})"


def location_out(geom: object | None) -> GeoPointOut | None:
    """Convert a GeoAlchemy2 geometry value to the API's plain lat/lon shape.
    Public: core_api.detections.service also needs this to render a route's
    per-hop camera location, so it is not a registry-internal helper."""
    if geom is None:
        return None
    point = to_shape(geom)  # type: ignore[arg-type]
    return GeoPointOut(lat=point.y, lon=point.x)


async def get_or_create_department(session: AsyncSession, name: str) -> Department:
    result = await session.execute(select(Department).where(Department.name == name))
    department = result.scalar_one_or_none()
    if department is not None:
        return department

    department = Department(name=name)
    session.add(department)
    await session.flush()  # assigns department.id without committing
    return department


async def get_or_create_site(
    session: AsyncSession, department_id: uuid.UUID, name: str, location: GeoPointOut | None
) -> Site:
    result = await session.execute(
        select(Site).where(Site.department_id == department_id, Site.name == name)
    )
    site = result.scalar_one_or_none()
    if site is not None:
        return site

    site = Site(
        department_id=department_id,
        name=name,
        location=_point_wkt(location.lat, location.lon) if location else None,
    )
    session.add(site)
    await session.flush()
    return site


async def upsert_camera(
    session: AsyncSession,
    *,
    camera_id: str,
    name: str,
    driver_id: str,
    department_name: str | None,
    site_name: str | None,
    location: GeoPointOut | None,
    tier: str,
    status: str,
    source: str,
    attributes: dict[str, str],
    profiles: Sequence[StreamProfileIn] | Sequence[Mapping[str, object]],
) -> Camera:
    """Insert a camera, or update it in place if `camera_id` already exists.

    A single upsert path for manual entry, bulk CSV and catalogue
    reconciliation — see the module docstring.
    """
    department = (
        await get_or_create_department(session, department_name) if department_name else None
    )
    site = (
        await get_or_create_site(session, department.id, site_name, location)
        if site_name and department is not None
        else None
    )

    result = await session.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()

    location_wkt = _point_wkt(location.lat, location.lon) if location else None

    if camera is None:
        camera = Camera(
            camera_id=camera_id,
            name=name,
            driver_id=driver_id,
            department_id=department.id if department else None,
            site_id=site.id if site else None,
            location=location_wkt,
            tier=tier,
            status=status,
            source=source,
            attributes=attributes,
        )
        session.add(camera)
    else:
        camera.name = name
        camera.driver_id = driver_id
        camera.department_id = department.id if department else camera.department_id
        camera.site_id = site.id if site else camera.site_id
        camera.location = location_wkt or camera.location
        camera.tier = tier
        camera.status = status
        camera.source = source
        camera.attributes = attributes

    await session.flush()

    # Replace stream profiles wholesale — simpler and correct for a catalogue
    # entry that dropped/renamed a protocol between runs, at the cost of
    # regenerating surrogate ids on every reconciliation (acceptable: nothing
    # references a stream_profiles.id across requests).
    await session.execute(delete(StreamProfile).where(StreamProfile.camera_id == camera_id))
    for profile in profiles:
        data: Mapping[str, object] = (
            profile if isinstance(profile, Mapping) else profile.model_dump()
        )
        session.add(StreamProfile(camera_id=camera_id, **data))

    await session.flush()
    # Eager-load every relationship/column camera_to_out() touches. Async
    # sessions do not support implicit lazy-loading on attribute access (it
    # needs a sync IO call from inside an async context, which raises
    # exactly the "MissingGreenlet" error this project hit once already) —
    # so every relationship the output mapper needs must be refreshed
    # explicitly here. `location`/`fov` matter too: without refreshing them,
    # the in-memory object still holds the raw WKT string this function
    # assigned before flush, not the WKBElement a real round-trip produces,
    # and geoalchemy2.shape.to_shape() rejects a plain string.
    await session.refresh(
        camera, attribute_names=["profiles", "department", "site", "location", "fov"]
    )
    return camera


@dataclass(slots=True)
class UpsertSummary:
    """What a batch catalogue sync actually did — surfaced in the ops
    dashboard and the reconciliation job's own logs."""

    onboarded: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    """(camera_id, error message) — one bad entry never blocks the batch."""

    @property
    def total(self) -> int:
        return len(self.onboarded) + len(self.updated)


async def upsert_from_descriptors(
    session: AsyncSession, descriptors: list[CameraDescriptor], *, source: str
) -> UpsertSummary:
    """Catalogue-driven onboarding: every run starts from the catalogue and
    upserts every entry it can. camera_id is the only thing ever hard-coded
    is nothing — this reads it fresh from the descriptor every time."""
    summary = UpsertSummary()
    for descriptor in descriptors:
        try:
            existed = (
                await session.execute(
                    select(Camera.camera_id).where(Camera.camera_id == descriptor.camera_id)
                )
            ).scalar_one_or_none() is not None

            location = (
                GeoPointOut(lat=descriptor.location.lat, lon=descriptor.location.lon)
                if descriptor.location
                else None
            )
            await upsert_camera(
                session,
                camera_id=descriptor.camera_id,
                name=descriptor.name,
                driver_id=descriptor.driver_id,
                department_name=descriptor.department,
                site_name=descriptor.site,
                location=location,
                tier=descriptor.tier.value,
                status=descriptor.status.value,
                source=source,
                attributes=descriptor.attributes,
                profiles=[
                    {
                        "protocol": p.protocol.value,
                        "url": p.url,
                        "codec": p.codec,
                        "width": p.width,
                        "height": p.height,
                        "declared_fps": p.declared_fps,
                    }
                    for p in descriptor.profiles
                ],
            )
            (summary.updated if existed else summary.onboarded).append(descriptor.camera_id)
        except Exception as exc:
            summary.failed.append((descriptor.camera_id, str(exc)))
    return summary


async def get_camera(session: AsyncSession, camera_id: str) -> Camera | None:
    result = await session.execute(
        select(Camera)
        .where(Camera.camera_id == camera_id)
        .options(
            selectinload(Camera.profiles),
            selectinload(Camera.department),
            selectinload(Camera.site),
        )
    )
    return result.scalar_one_or_none()


async def list_cameras(
    session: AsyncSession, *, department_name: str | None = None
) -> list[Camera]:
    query = select(Camera).options(
        selectinload(Camera.profiles), selectinload(Camera.department), selectinload(Camera.site)
    )
    if department_name:
        query = query.join(Department).where(Department.name == department_name)
    result = await session.execute(query.order_by(Camera.camera_id))
    return list(result.scalars().all())


async def codecs_in_use(session: AsyncSession) -> list[str]:
    """Distinct codecs currently declared across live cameras' stream
    profiles — backs the Integrator Compliance panel's "mixed-codec
    handling" tick: proof by observation (two-plus codecs live right now),
    not a static claim."""
    result = await session.execute(
        select(StreamProfile.codec)
        .join(Camera, Camera.camera_id == StreamProfile.camera_id)
        .where(Camera.status == "live", StreamProfile.codec.is_not(None))
        .distinct()
    )
    return sorted({codec for (codec,) in result.all() if codec})


async def list_departments(session: AsyncSession) -> list[DepartmentOut]:
    from sqlalchemy import func

    result = await session.execute(
        select(Department, func.count(Camera.camera_id))
        .outerjoin(Camera, Camera.department_id == Department.id)
        .group_by(Department.id)
        .order_by(Department.name)
    )
    return [
        DepartmentOut(id=dept.id, name=dept.name, code=dept.code, camera_count=count)
        for dept, count in result.all()
    ]


def camera_to_out(camera: Camera) -> CameraOut:
    return CameraOut(
        camera_id=camera.camera_id,
        name=camera.name,
        driver_id=camera.driver_id,
        department_name=camera.department.name if camera.department else None,
        site_name=camera.site.name if camera.site else None,
        location=location_out(camera.location),
        tier=camera.tier,
        status=camera.status,
        last_seen_at=camera.last_seen_at,
        measured_fps=camera.measured_fps,
        declared_fps=camera.declared_fps,
        reconnects=camera.reconnects,
        discontinuities=camera.discontinuities,
        tamper_status=camera.tamper_status,
        source=camera.source,
        attributes=camera.attributes,
        profiles=[StreamProfileOut.model_validate(p) for p in camera.profiles],
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


async def update_camera_health(
    session: AsyncSession, camera_id: str, update: CameraHealthUpdate
) -> Camera | None:
    """Applied by an edge worker's periodic heartbeat. Only the fields the
    worker actually reports are touched — a heartbeat that omits
    measured_fps (e.g. a camera that hasn't produced a frame yet) must not
    stomp the last known value with None."""
    camera = await get_camera(session, camera_id)
    if camera is None:
        return None

    camera.status = update.status
    camera.last_seen_at = datetime.now(UTC)
    if update.measured_fps is not None:
        camera.measured_fps = update.measured_fps
    if update.declared_fps is not None:
        camera.declared_fps = update.declared_fps
    if update.reconnects is not None:
        camera.reconnects = update.reconnects
    if update.discontinuities is not None:
        camera.discontinuities = update.discontinuities
    if update.tamper_status is not None:
        camera.tamper_status = update.tamper_status

    await session.flush()
    # `updated_at` is server-generated (onupdate=func.now()) so the flush
    # above marks it expired on this ORM instance; refresh it explicitly
    # rather than let an implicit reload happen outside async/greenlet
    # context the next time something reads it (MissingGreenlet) — the same
    # class of bug as the relationship-refresh gotcha in upsert_camera.
    await session.refresh(camera, attribute_names=["updated_at"])
    return camera


def department_to_out(department: Department, camera_count: int = 0) -> DepartmentOut:
    return DepartmentOut(
        id=department.id, name=department.name, code=department.code, camera_count=camera_count
    )


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _same_relay_host(hostname: str, relay_hostname: str) -> bool:
    """`localhost` and `127.0.0.1` are the same machine but not the same
    string — a raw netloc comparison treated the synthetic grid's own
    cameras (registered as `127.0.0.1:8554`) as an unrecognised external
    source whenever `relay_rtsp_url` was configured with `localhost`
    instead, which is exactly the default in sentinel_core.config."""
    if hostname == relay_hostname:
        return True
    return hostname in _LOOPBACK_HOSTS and relay_hostname in _LOOPBACK_HOSTS


async def _ensure_external_relay_path(
    *,
    rtsp_url: str,
    path_name: str,
    settings: Settings,
    client: httpx.AsyncClient,
) -> bool:
    """Makes MediaMTX relay `rtsp_url` locally under `path_name`, as an
    on-demand PULL source, so the browser never sees the camera's own
    (often credentialed) URL and the compliance guide's "consume only, never
    publish to the gateway" holds: MediaMTX itself opens the RTSP connection
    as a client, exactly like `edge_agent`'s own capture does, and nothing is
    pushed anywhere. `sourceOnDemand` means MediaMTX doesn't actually dial the
    camera until a viewer first requests the path, so registering 30 cameras
    up front costs nothing until someone actually opens one.

    Idempotent and safe under a race: if the path already exists (a concurrent
    request beat this one to it), MediaMTX's `add` returns 400 with a specific
    "path already exists" error — treated as success, not a failure, since the
    desired end state (the path exists) is exactly what happened either way.

    Returns whether the path is now known to exist. Never raises — a
    MediaMTX outage must degrade to "preview unavailable", not a 500 on the
    whole Cameras screen.
    """
    add_url = f"{settings.relay_api_url}/v3/config/paths/add/{path_name}"
    try:
        get_response = await client.get(f"{settings.relay_api_url}/v3/config/paths/get/{path_name}")
        if get_response.status_code == 200:
            return True
        add_response = await client.post(
            add_url,
            json={"source": rtsp_url, "sourceOnDemand": True, "rtspTransport": "tcp"},
        )
        if add_response.status_code == 200:
            return True
        if add_response.status_code == 400 and "already exists" in add_response.text:
            return True
        logger.warning(
            "MediaMTX refused to add relay path %r: %s %s",
            path_name,
            add_response.status_code,
            add_response.text,
        )
        return False
    except httpx.HTTPError as exc:
        logger.warning("could not reach the local relay to add path %r: %s", path_name, exc)
        return False


async def resolve_camera_stream(
    camera: Camera, settings: Settings, *, client: httpx.AsyncClient | None = None
) -> CameraStreamOut:
    """The Cameras screen's "view live" action needs one thing: a URL a
    plain <video> tag can play with zero credentials of its own — never a
    camera's raw RTSP/WHEP profile, which for gov-catalogue cameras carries
    an embedded email:password (see routers/registry.py's docstring on this
    endpoint for why that must never reach the browser).

    Two cases:
    1. The camera is already relayed through *our own* local MediaMTX (the M1
       synthetic grid, published to `dev/*` — see infra/compose/mediamtx.yml):
       its RTSP profile host matches `settings.relay_rtsp_url`, so the
       equivalent local, unauthenticated HLS URL is derived directly by
       swapping the scheme/host for the relay's HLS host and keeping the RTSP
       path.
    2. The camera is external (gov-catalogue or, eventually, a department's
       own ONVIF camera): its credentialed RTSP URL is never handed to the
       browser. Instead, MediaMTX is told (via its own control API — never
       the government's) to PULL that RTSP feed itself, republished locally
       under `{relay_external_path_prefix}/{camera_id}`, and *that* local,
       credential-free HLS URL is returned instead.
    """
    rtsp_profile = next((p for p in camera.profiles if p.protocol == "rtsp"), None)
    if rtsp_profile is None:
        return CameraStreamOut(available=False, reason="This camera has no RTSP profile on file.")

    relay = urlsplit(settings.relay_rtsp_url)
    parsed = urlsplit(rtsp_profile.url)
    same_host = (
        parsed.hostname is not None
        and relay.hostname is not None
        and _same_relay_host(parsed.hostname, relay.hostname)
    )
    if same_host and parsed.port == relay.port:
        hls_url = f"{settings.relay_hls_url.rstrip('/')}{parsed.path}/index.m3u8"
        return CameraStreamOut(available=True, hls_url=hls_url)

    path_name = f"{settings.relay_external_path_prefix}/{camera.camera_id}"
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=5.0)
    try:
        ok = await _ensure_external_relay_path(
            rtsp_url=rtsp_profile.url, path_name=path_name, settings=settings, client=client
        )
    finally:
        if owns_client:
            await client.aclose()

    if not ok:
        return CameraStreamOut(
            available=False,
            reason=(
                "Couldn't reach the local relay to proxy this camera's feed — it may be "
                "temporarily down."
            ),
        )
    hls_url = f"{settings.relay_hls_url.rstrip('/')}/{path_name}/index.m3u8"
    return CameraStreamOut(available=True, hls_url=hls_url)
