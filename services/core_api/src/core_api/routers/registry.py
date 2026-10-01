"""Registry HTTP API — Model 1 (mandatory): the camera inventory and its GIS
coverage view. See docs/01-ARCHITECTURE.md section 4 and docs/03-UX-DESIGN.md
section 4.6 for the screens this backs."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.audit.service import record_audit_event
from core_api.auth.dependencies import (
    current_user,
    current_user_or_service,
    require_role,
    require_service_token,
)
from core_api.auth.service import TokenPayload
from core_api.db.base import get_session
from core_api.registry.bulk_import import BulkImportResult, parse_and_import_csv
from core_api.registry.gap_analysis import compute_coverage_gaps
from core_api.registry.lifecycle import (
    LifecycleReport,
    build_lifecycle_report,
    lifecycle_report_csv,
)
from core_api.registry.schemas import (
    CameraCreate,
    CameraHealthUpdate,
    CameraOut,
    CameraStreamOut,
    CoverageGapReport,
    DepartmentOut,
    DeviceDiscoveryRequest,
    DeviceDiscoveryResult,
    DiscoveredCameraOut,
    GeoPointOut,
)
from core_api.registry.service import (
    camera_to_out,
    get_camera,
    list_cameras,
    list_departments,
    resolve_camera_stream,
    update_camera_health,
    upsert_camera,
    upsert_from_descriptors,
)
from sentinel_core.config import get_settings
from sentinel_core.drivers import DahuaSource, DiscoveryScope, HikvisionSource, OnvifSource
from sentinel_core.gov_catalogue import GovCatalogueClient
from sentinel_core.schemas.camera import CameraDescriptor, GeoPoint
from sentinel_core.stream_urls import redact_credentials

router = APIRouter(prefix="/api/v1", tags=["registry"])


def _require_admin(user: TokenPayload | None) -> None:
    """Registry writes change what every department sees and what the edge
    workers dial, so they are an administrator's action. None is the edge
    worker's service token, which is trusted for its own registrations."""
    if user is not None and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator can change the registry")


@router.get("/cameras", response_model=list[CameraOut])
async def list_cameras_endpoint(
    department: str | None = Query(default=None, description="Filter by department name"),
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> list[CameraOut]:
    cameras = await list_cameras(session, department_name=department)
    return [camera_to_out(c) for c in cameras]


@router.get("/edge/cameras", response_model=list[CameraOut])
async def edge_camera_manifest_endpoint(
    session: AsyncSession = Depends(get_session),
    _svc: None = Depends(require_service_token),
) -> list[CameraOut]:
    """What an edge worker started with `--source registry` analyses: every
    camera in the registry, however it was onboarded (manual, bulk CSV,
    device discovery, catalogue), with its stream URLs intact. Service-token
    only — the one place credentialed URLs leave the API, and never to a
    browser (see camera_to_out)."""
    cameras = await list_cameras(session)
    return [camera_to_out(c, reveal_credentials=True) for c in cameras]


@router.get("/cameras/{camera_id}", response_model=CameraOut)
async def get_camera_endpoint(
    camera_id: str,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> CameraOut:
    camera = await get_camera(session, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"no camera with id {camera_id!r}")
    return camera_to_out(camera)


@router.post("/cameras", response_model=CameraOut, status_code=201)
async def create_camera_endpoint(
    payload: CameraCreate,
    session: AsyncSession = Depends(get_session),
    actor: TokenPayload | None = Depends(current_user_or_service),
) -> CameraOut:
    # The edge worker (service token, actor None) registers catalogue
    # cameras; a human adding one to the estate must be an administrator.
    _require_admin(actor)
    existing = await get_camera(session, payload.camera_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"camera {payload.camera_id!r} already exists")

    camera = await upsert_camera(
        session,
        camera_id=payload.camera_id,
        name=payload.name,
        driver_id=payload.driver_id,
        department_name=payload.department_name,
        site_name=payload.site_name,
        location=payload.location,
        tier=payload.tier,
        status="unknown",
        source="manual",
        attributes=payload.attributes,
        profiles=payload.profiles,
    )
    if actor is not None:
        await record_audit_event(
            session,
            actor_email=actor.email,
            action="camera_onboarded",
            resource_type="camera",
            resource_id=payload.camera_id,
            detail={"source": "manual", "department": payload.department_name or ""},
        )
    await session.commit()
    return camera_to_out(camera)


@router.patch("/cameras/{camera_id}/health", response_model=CameraOut)
async def update_camera_health_endpoint(
    camera_id: str,
    payload: CameraHealthUpdate,
    session: AsyncSession = Depends(get_session),
    _svc: None = Depends(require_service_token),
) -> CameraOut:
    """Called by an edge worker's periodic heartbeat, and opportunistically
    by detection ingest (see core_api.detections.service.ingest_detection).
    Gated by a shared service token, not a user login — the edge worker has
    no human operator to log in as (see auth/dependencies.py)."""
    camera = await update_camera_health(session, camera_id, payload)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"no camera with id {camera_id!r}")
    await session.commit()
    return camera_to_out(camera)


@router.get("/cameras/{camera_id}/stream", response_model=CameraStreamOut)
async def camera_stream_endpoint(
    camera_id: str,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> CameraStreamOut:
    """Resolves a URL the Cameras screen's live-preview can hand straight to
    a <video> tag — never the camera's own RTSP/WHEP profile, which for a
    gov-catalogue camera carries embedded credentials (email:password) that
    must never reach the browser. See registry/service.py's
    resolve_camera_stream for what "available" actually means today."""
    camera = await get_camera(session, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"no camera with id {camera_id!r}")
    return await resolve_camera_stream(camera, get_settings())


@router.post("/cameras/bulk-import", response_model=BulkImportResult)
async def bulk_import_endpoint(
    file: UploadFile,
    dry_run: bool = Query(default=True, description="Preview only; nothing is written when true"),
    session: AsyncSession = Depends(get_session),
    user: TokenPayload = Depends(current_user),
) -> BulkImportResult:
    if not dry_run:
        _require_admin(user)  # previewing a file is harmless; changing the estate is not
    content = (await file.read()).decode("utf-8-sig")  # -sig: tolerate an Excel-exported BOM
    result = await parse_and_import_csv(session, content, dry_run=dry_run)
    if not dry_run:
        await record_audit_event(
            session,
            actor_email=user.email,
            action="cameras_bulk_imported",
            resource_type="camera",
            detail={
                "file": file.filename or "",
                "succeeded": result.succeeded,
                "failed": result.failed,
                "camera_ids": [r.camera_id for r in result.rows if r.ok and r.camera_id],
            },
        )
        await session.commit()
    return result


@router.post("/cameras/discover", response_model=dict)
async def discover_from_catalogue_endpoint(
    session: AsyncSession = Depends(get_session),
    user: TokenPayload = Depends(current_user),
) -> dict[str, object]:
    """Catalogue-driven onboarding: fetch the government catalogue right now
    and upsert every camera it lists. Never hard-codes a camera id — see
    tests/test_compliance.py. Administrators only."""
    _require_admin(user)
    settings = get_settings()
    async with GovCatalogueClient(settings) as client:
        descriptors = await client.fetch()

    summary = await upsert_from_descriptors(session, descriptors, source="gov_catalogue")
    await record_audit_event(
        session,
        actor_email=user.email,
        action="cameras_discovered",
        resource_type="camera",
        detail={
            "source": "gov_catalogue",
            "onboarded": len(summary.onboarded),
            "updated": len(summary.updated),
            "failed": len(summary.failed),
        },
    )
    await session.commit()

    return {
        "fetched": len(descriptors),
        "onboarded": summary.onboarded,
        "updated": summary.updated,
        "failed": [{"camera_id": cam_id, "error": err} for cam_id, err in summary.failed],
    }


def _device_source(
    request: DeviceDiscoveryRequest,
) -> OnvifSource | HikvisionSource | DahuaSource:
    password = request.password.get_secret_value() if request.password else None
    if request.driver == "onvif":
        return OnvifSource(username=request.username, password=password)
    if request.driver == "hikvision":
        return HikvisionSource(username=request.username or "admin", password=password or "")
    return DahuaSource(username=request.username or "admin", password=password or "")


@router.post("/cameras/discover-device", response_model=DeviceDiscoveryResult)
async def discover_device_endpoint(
    payload: DeviceDiscoveryRequest,
    session: AsyncSession = Depends(get_session),
    admin: TokenPayload = Depends(require_role("admin")),
) -> DeviceDiscoveryResult:
    """Directed discovery against one device on the camera network: ask it
    what streams it has, then (unless `dry_run`) onboard each as a camera.
    Admin-only because it dials into another department's equipment with
    that department's credentials."""
    try:
        descriptors = await _device_source(payload).discover(DiscoveryScope(host=payload.host))
    except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
        # ParseError: the wrong device type was chosen, or the address serves
        # a web page rather than the vendor's XML API.
        raise HTTPException(
            status_code=502,
            detail=f"could not query {payload.driver} device at {payload.host}: {exc}",
        ) from exc

    location = (
        GeoPoint(lat=payload.location.lat, lon=payload.location.lon) if payload.location else None
    )
    descriptors = [
        CameraDescriptor.model_validate(
            d.model_dump()
            | {
                "department": payload.department_name or d.department,
                "site": payload.site_name or d.site,
                "location": location or d.location,
            }
        )
        for d in descriptors
    ]
    result = DeviceDiscoveryResult(
        dry_run=payload.dry_run,
        discovered=[
            DiscoveredCameraOut(
                camera_id=d.camera_id,
                name=d.name,
                stream_count=len(d.profiles),
                stream_urls=[redact_credentials(p.url) for p in d.profiles],
            )
            for d in descriptors
        ],
    )
    if payload.dry_run:
        return result

    source = f"{payload.driver}_discovery"
    summary = await upsert_from_descriptors(session, descriptors, source=source)
    await record_audit_event(
        session,
        actor_email=admin.email,
        action="cameras_discovered",
        resource_type="camera",
        detail={
            "source": source,
            "host": payload.host,
            "onboarded": summary.onboarded,
            "updated": summary.updated,
            "failed": len(summary.failed),
        },
    )
    await session.commit()
    result.onboarded = summary.onboarded
    result.updated = summary.updated
    result.failed = [{"camera_id": cam_id, "error": err} for cam_id, err in summary.failed]
    return result


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments_endpoint(
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> list[DepartmentOut]:
    return await list_departments(session)


@router.get("/coverage/gaps", response_model=CoverageGapReport)
async def coverage_gaps_endpoint(
    coverage_radius_m: float = Query(default=500.0, gt=0),
    cell_size_m: float = Query(default=250.0, gt=0),
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> CoverageGapReport:
    return await compute_coverage_gaps(
        session, coverage_radius_m=coverage_radius_m, cell_size_m=cell_size_m
    )


@router.get("/coverage/lifecycle", response_model=LifecycleReport)
async def lifecycle_report_endpoint(
    ageing_years: float = Query(default=5.0, gt=0, description="Age at which a camera is ageing"),
    amc_warning_days: int = Query(default=60, ge=0, description="Flag AMCs expiring this soon"),
    department: str | None = Query(default=None, description="Filter by department name"),
    output_format: str = Query(default="json", alias="format", pattern="^(json|csv)$"),
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> LifecycleReport | Response:
    """The ageing-infrastructure and maintenance half of the gap analysis:
    cameras past their service life, AMCs lapsed or about to, cameras
    flagged for maintenance, and cameras currently offline — by department.
    `format=csv` downloads the cameras needing attention as a work list."""
    cameras = await list_cameras(session, department_name=department)
    report = build_lifecycle_report(
        cameras, ageing_threshold_years=ageing_years, amc_warning_days=amc_warning_days
    )
    if output_format == "csv":
        return Response(
            content=lifecycle_report_csv(report),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="camera-lifecycle-{report.as_of.isoformat()}.csv"'
                )
            },
        )
    return report


# GeoPointOut is re-exported at module scope so FastAPI's OpenAPI generator
# resolves it as a named schema (referenced by CameraCreate.location) rather
# than an anonymous inline object.
__all__ = ["GeoPointOut", "router"]
