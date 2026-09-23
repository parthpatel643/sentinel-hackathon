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
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Detection
from sentinel_core.config import Settings

__all__ = [
    "RevealAuditEvent",
    "record_reveal_audit",
    "resolve_original_path",
    "resolve_snapshot_path",
]

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True, slots=True)
class RevealAuditEvent:
    event_id: str
    actor_email: str
    reason: str
    revealed_at: datetime


def record_reveal_audit(*, event_id: str, actor_email: str, reason: str) -> RevealAuditEvent:
    """Logs the reveal for audit purposes — a structured log line today
    (genuinely reaching stdout since the M12 mTLS work's logging fix; see
    docs/08-SECURITY-HARDENING.md), a durable hash-chained row once the
    audit-log milestone gives every sensitive action a permanent home. The
    *reason* is exactly what docs/05-DELIVERY-PLAN.md's "reveal-on-
    authorisation with reason capture" calls for — captured here, not
    merely accepted and discarded."""
    event = RevealAuditEvent(
        event_id=event_id, actor_email=actor_email, reason=reason, revealed_at=datetime.now(UTC)
    )
    logger.info(
        "face_reveal_audit",
        extra={
            "event_id": event.event_id,
            "actor_email": event.actor_email,
            "reason": event.reason,
            "revealed_at": event.revealed_at.isoformat(),
        },
    )
    return event
