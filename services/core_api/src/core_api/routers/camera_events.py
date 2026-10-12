"""Camera view alerts: a camera knocked, re-aimed or obstructed.

Ingest and evidence upload are service-token gated (the edge worker's view
monitor reports them); reading and triage need a login, and every triage is
audited. New and updated alerts are pushed to every console like zone events."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.audit.service import record_audit_event
from core_api.auth.dependencies import (
    current_user,
    current_user_or_signed_url,
    require_service_token,
)
from core_api.auth.service import TokenPayload
from core_api.camera_events.schemas import (
    CameraEventIn,
    CameraEventOut,
    CameraEventUpdate,
    CameraRestoredIn,
)
from core_api.camera_events.service import (
    list_camera_events,
    record_camera_event,
    record_view_restored,
    update_camera_event,
)
from core_api.db.base import get_session
from core_api.db.models import CameraEvent
from core_api.events.broker import publish_models
from sentinel_core.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["camera-events"])

Which = Literal["before", "after"]
_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
_JPEG_MAGIC = b"\xff\xd8\xff"


def _out(event: CameraEvent) -> CameraEventOut:
    return CameraEventOut.model_validate(event)


async def _publish(session: AsyncSession, events: list[CameraEvent]) -> None:
    outs = [_out(e) for e in events]
    await publish_models(session, "camera_event", [(o.camera_id, o) for o in outs])


@router.post("/camera-events", response_model=CameraEventOut, status_code=201)
async def record_camera_event_endpoint(
    payload: CameraEventIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _svc: None = Depends(require_service_token),
) -> CameraEventOut:
    """201 with a new alert, or 200 with the one already open for this camera
    and kind — a camera that stays moved is one alert, not many."""
    event, created = await record_camera_event(session, payload)
    await session.commit()
    if created:
        await _publish(session, [event])
    else:
        response.status_code = 200
    return _out(event)


@router.post("/camera-events/restored", response_model=list[CameraEventOut])
async def record_view_restored_endpoint(
    payload: CameraRestoredIn,
    session: AsyncSession = Depends(get_session),
    _svc: None = Depends(require_service_token),
) -> list[CameraEventOut]:
    events = await record_view_restored(session, payload)
    await session.commit()
    await _publish(session, events)
    return [_out(e) for e in events]


@router.get("/camera-events", response_model=list[CameraEventOut])
async def list_camera_events_endpoint(
    status: str | None = Query(default=None, description="new | acknowledged | resolved | ..."),
    camera_id: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload = Depends(current_user),
) -> list[CameraEventOut]:
    events = await list_camera_events(session, status=status, camera_id=camera_id, limit=limit)
    return [_out(e) for e in events]


@router.patch("/camera-events/{event_id}", response_model=CameraEventOut)
async def update_camera_event_endpoint(
    event_id: uuid.UUID,
    payload: CameraEventUpdate,
    session: AsyncSession = Depends(get_session),
    user: TokenPayload = Depends(current_user),
) -> CameraEventOut:
    event = await update_camera_event(
        session, event_id, status=payload.status, resolved_by=user.email
    )
    if event is None:
        raise HTTPException(status_code=404, detail=f"no camera event with id {event_id}")
    await record_audit_event(
        session,
        actor_email=user.email,
        action="camera_event_status_changed",
        resource_type="camera_event",
        resource_id=str(event_id),
        detail={"status": payload.status, "camera_id": event.camera_id, "note": payload.note or ""},
    )
    await session.commit()
    await _publish(session, [event])
    return _out(event)


def _snapshot_path(event_id: str, which: Which) -> Path:
    return Path(get_settings().snapshots_dir) / f"{event_id}-{which}.jpg"


@router.put("/camera-events/{event_id}/snapshot/{which}", status_code=204)
async def upload_camera_event_snapshot_endpoint(
    event_id: str,
    which: Which,
    blurred: UploadFile,
    _svc: None = Depends(require_service_token),
) -> Response:
    """A worker on another machine hands over the face-blurred before/after
    frames it wrote locally. One beside the API shares the directory."""
    if not _valid_id(event_id):
        raise HTTPException(status_code=422, detail="invalid event id")
    data = await blurred.read(_MAX_SNAPSHOT_BYTES + 1)
    if len(data) > _MAX_SNAPSHOT_BYTES:
        raise HTTPException(status_code=413, detail="snapshot larger than 8 MB")
    if not data.startswith(_JPEG_MAGIC):
        raise HTTPException(status_code=415, detail="snapshot is not a JPEG")
    path = _snapshot_path(event_id, which)

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f".{path.name}.part")
        partial.write_bytes(data)
        partial.replace(path)

    await asyncio.to_thread(_write)
    return Response(status_code=204)


@router.get("/camera-events/{event_id}/snapshot/{which}")
async def camera_event_snapshot_endpoint(
    event_id: str,
    which: Which,
    session: AsyncSession = Depends(get_session),
    _user: TokenPayload | None = Depends(current_user_or_signed_url),
) -> FileResponse:
    """The remembered view (before) or the view when the change was confirmed
    (after), face-blurred like every evidence frame. Served only for an event
    the caller can see, so department scoping covers the frames too."""
    if not _valid_id(event_id):
        raise HTTPException(status_code=422, detail="invalid event id")
    visible = await session.scalar(select(CameraEvent.id).where(CameraEvent.event_id == event_id))
    if visible is None:
        raise HTTPException(status_code=404, detail="No snapshot on file for this camera event.")
    path = _snapshot_path(event_id, which)
    if not await asyncio.to_thread(path.is_file):
        raise HTTPException(status_code=404, detail="No snapshot on file for this camera event.")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)


def _valid_id(event_id: str) -> bool:
    return 0 < len(event_id) <= 64 and all(c.isalnum() or c in "_-" for c in event_id)
