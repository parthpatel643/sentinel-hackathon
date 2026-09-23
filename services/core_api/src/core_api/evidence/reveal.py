"""Snapshot serving + reveal-on-authorisation — the core_api half of M12's
edge-side default face blurring. The edge worker (services/edge_agent's
SnapshotWriter) already wrote both artefacts to a shared filesystem path;
this module only ever *reads* them, resolved by `event_id` convention
rather than trusting any raw path from the wire (`Detection.snapshot_uri`
is an opaque `snapshot://<event_id>` marker, never a filesystem path — see
docs/08-SECURITY-HARDENING.md).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.audit.service import record_audit_event
from core_api.db.models import AuditLogEntry, Detection
from sentinel_core.config import Settings

__all__ = ["record_reveal_audit", "resolve_original_path", "resolve_snapshot_path"]


async def _detection_has_snapshot(session: AsyncSession, event_id: str) -> bool:
    result = await session.execute(
        select(Detection.snapshot_uri).where(Detection.event_id == event_id)
    )
    snapshot_uri = result.scalar_one_or_none()
    return bool(snapshot_uri)


async def resolve_snapshot_path(
    session: AsyncSession, event_id: str, settings: Settings
) -> Path | None:
    """The default, face-blurred snapshot — safe to serve to any
    authenticated user, no reason capture required."""
    if not await _detection_has_snapshot(session, event_id):
        return None
    path = Path(settings.snapshots_dir) / f"{event_id}.jpg"
    return path if await asyncio.to_thread(path.is_file) else None


async def resolve_original_path(
    session: AsyncSession, event_id: str, settings: Settings
) -> Path | None:
    """The unblurred original — only ever called from the reveal endpoint,
    which requires an elevated role and a captured reason first."""
    if not await _detection_has_snapshot(session, event_id):
        return None
    path = Path(settings.snapshot_originals_dir) / f"{event_id}.jpg"
    return path if await asyncio.to_thread(path.is_file) else None


async def record_reveal_audit(
    session: AsyncSession, *, event_id: str, actor_email: str, reason: str
) -> AuditLogEntry:
    """Persists the reveal to the hash-chained audit log — the *reason* is
    exactly what docs/05-DELIVERY-PLAN.md's "reveal-on-authorisation with
    reason capture" calls for, captured here, not merely accepted and
    discarded. Callers must still `session.commit()` — this only flushes,
    matching every other service function in this codebase."""
    return await record_audit_event(
        session,
        actor_email=actor_email,
        action="face_reveal",
        resource_type="detection",
        resource_id=event_id,
        detail={"reason": reason},
    )
