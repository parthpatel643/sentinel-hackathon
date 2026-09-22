"""Registry HTTP API — Model 1 (mandatory): the camera inventory and its GIS
coverage view. See docs/01-ARCHITECTURE.md section 4 and docs/03-UX-DESIGN.md
section 4.6 for the screens this backs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.base import get_session
from core_api.registry.bulk_import import BulkImportResult, parse_and_import_csv
from core_api.registry.gap_analysis import compute_coverage_gaps
from core_api.registry.schemas import (
    CameraCreate,
    CameraHealthUpdate,
    CameraOut,
    CameraStreamOut,
    CoverageGapReport,
    DepartmentOut,
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
from sentinel_core.gov_catalogue import GovCatalogueClient

router = APIRouter(prefix="/api/v1", tags=["registry"])


@router.get("/cameras", response_model=list[CameraOut])
async def list_cameras_endpoint(
    department: str | None = Query(default=None, description="Filter by department name"),
    session: AsyncSession = Depends(get_session),
) -> list[CameraOut]:
    cameras = await list_cameras(session, department_name=department)
    return [camera_to_out(c) for c in cameras]


@router.get("/cameras/{camera_id}", response_model=CameraOut)
async def get_camera_endpoint(
    camera_id: str, session: AsyncSession = Depends(get_session)
) -> CameraOut:
    camera = await get_camera(session, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"no camera with id {camera_id!r}")
    return camera_to_out(camera)


@router.post("/cameras", response_model=CameraOut, status_code=201)
async def create_camera_endpoint(
    payload: CameraCreate, session: AsyncSession = Depends(get_session)
) -> CameraOut:
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
    await session.commit()
    return camera_to_out(camera)


@router.patch("/cameras/{camera_id}/health", response_model=CameraOut)
async def update_camera_health_endpoint(
    camera_id: str,
    payload: CameraHealthUpdate,
    session: AsyncSession = Depends(get_session),
) -> CameraOut:
    """Called by an edge worker's periodic heartbeat, and opportunistically
    by detection ingest (see core_api.detections.service.ingest_detection).
    Not authenticated yet — see docs/05-DELIVERY-PLAN.md's hardening backlog."""
    camera = await update_camera_health(session, camera_id, payload)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"no camera with id {camera_id!r}")
    await session.commit()
    return camera_to_out(camera)


@router.get("/cameras/{camera_id}/stream", response_model=CameraStreamOut)
async def camera_stream_endpoint(
    camera_id: str, session: AsyncSession = Depends(get_session)
) -> CameraStreamOut:
    """Resolves a URL the Cameras screen's live-preview can hand straight to
    a <video> tag — never the camera's own RTSP/WHEP profile, which for a
    gov-catalogue camera carries embedded credentials (email:password) that
    must never reach the browser. See registry/service.py's
    resolve_camera_stream for what "available" actually means today."""
    camera = await get_camera(session, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"no camera with id {camera_id!r}")
    return resolve_camera_stream(camera, get_settings())


@router.post("/cameras/bulk-import", response_model=BulkImportResult)
async def bulk_import_endpoint(
    file: UploadFile,
    dry_run: bool = Query(default=True, description="Preview only; nothing is written when true"),
    session: AsyncSession = Depends(get_session),
) -> BulkImportResult:
    content = (await file.read()).decode("utf-8-sig")  # -sig: tolerate an Excel-exported BOM
    result = await parse_and_import_csv(session, content, dry_run=dry_run)
    if not dry_run:
        await session.commit()
    return result


@router.post("/cameras/discover", response_model=dict)
async def discover_from_catalogue_endpoint(
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Catalogue-driven onboarding: fetch the government catalogue right now
    and upsert every camera it lists. Never hard-codes a camera id — see
    tests/test_compliance.py."""
    settings = get_settings()
    async with GovCatalogueClient(settings) as client:
        descriptors = await client.fetch()

    summary = await upsert_from_descriptors(session, descriptors, source="gov_catalogue")
    await session.commit()

    return {
        "fetched": len(descriptors),
        "onboarded": summary.onboarded,
        "updated": summary.updated,
        "failed": [{"camera_id": cam_id, "error": err} for cam_id, err in summary.failed],
    }


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments_endpoint(
    session: AsyncSession = Depends(get_session),
) -> list[DepartmentOut]:
    return await list_departments(session)


@router.get("/coverage/gaps", response_model=CoverageGapReport)
async def coverage_gaps_endpoint(
    coverage_radius_m: float = Query(default=500.0, gt=0),
    cell_size_m: float = Query(default=250.0, gt=0),
    session: AsyncSession = Depends(get_session),
) -> CoverageGapReport:
    return await compute_coverage_gaps(
        session, coverage_radius_m=coverage_radius_m, cell_size_m=cell_size_m
    )


# GeoPointOut is re-exported at module scope so FastAPI's OpenAPI generator
# resolves it as a named schema (referenced by CameraCreate.location) rather
# than an anonymous inline object.
__all__ = ["GeoPointOut", "router"]
