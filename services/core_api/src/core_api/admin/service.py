"""Retention policy preview + execution — docs/03-UX-DESIGN.md section 6:
"per-data-class retention sliders with a plain-language consequence preview
(\"Event clips will be deleted after 30 days. About 1.2 TB affected.\")",
and docs/05-DELIVERY-PLAN.md's M12 "retention policy engine." Preview only
ever reads; `execute_retention` is the real deletion this preview was
always in service of, gated by an admin-only endpoint and recorded in the
hash-chained audit log (every deletion is itself an audited action).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.admin.schemas import IntegrationStatusOut
from core_api.audit.service import record_audit_event
from core_api.db.models import AuditLogEntry, Detection, EvidenceClip
from sentinel_core.gov_registry import (
    AfisProvider,
    EGujCopProvider,
    PersonQuery,
    RegistryError,
    SarthiProvider,
    VahanProvider,
)

__all__ = [
    "RetentionExecutionResult",
    "RetentionPreview",
    "check_integration_statuses",
    "execute_retention",
    "list_audit_log",
    "preview_retention",
]


class RetentionPreview:
    def __init__(self, *, detections_affected: int, clips_affected: int, clips_bytes_affected: int):
        self.detections_affected = detections_affected
        self.clips_affected = clips_affected
        self.clips_bytes_affected = clips_bytes_affected


class RetentionExecutionResult:
    def __init__(self, *, detections_deleted: int, clips_deleted: int, clips_bytes_deleted: int):
        self.detections_deleted = detections_deleted
        self.clips_deleted = clips_deleted
        self.clips_bytes_deleted = clips_bytes_deleted


def _sum_existing_file_sizes(paths: list[str]) -> int:
    total = 0
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file():
            total += path.stat().st_size
    return total


def _delete_existing_files(paths: list[str]) -> None:
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file():
            path.unlink()


async def preview_retention(
    session: AsyncSession, *, detections_older_than_days: int, clips_older_than_days: int
) -> RetentionPreview:
    detections_cutoff = datetime.now(UTC) - timedelta(days=detections_older_than_days)
    clips_cutoff = datetime.now(UTC) - timedelta(days=clips_older_than_days)

    detections_affected = (
        await session.execute(
            select(func.count())
            .select_from(Detection)
            .where(Detection.observed_at < detections_cutoff)
        )
    ).scalar_one()

    clips_result = await session.execute(
        select(EvidenceClip.file_path).where(
            EvidenceClip.created_at < clips_cutoff, EvidenceClip.status == "sealed"
        )
    )
    clip_paths = [row[0] for row in clips_result.all() if row[0]]
    clips_bytes_affected = await asyncio.to_thread(_sum_existing_file_sizes, clip_paths)

    return RetentionPreview(
        detections_affected=detections_affected,
        clips_affected=len(clip_paths),
        clips_bytes_affected=clips_bytes_affected,
    )


async def execute_retention(
    session: AsyncSession,
    *,
    detections_older_than_days: int,
    clips_older_than_days: int,
    actor_email: str,
) -> RetentionExecutionResult:
    """The real deletion `preview_retention` was always previewing. Deletes
    sealed clips' files from disk *and* their rows, and detection rows
    older than the configured cutoffs — then records exactly what it did
    in the hash-chained audit log (docs/05-DELIVERY-PLAN.md's M12
    "retention policy engine" + "every human action is logged" from
    docs/01-ARCHITECTURE.md's design principles). Callers must still
    `session.commit()`."""
    detections_cutoff = datetime.now(UTC) - timedelta(days=detections_older_than_days)
    clips_cutoff = datetime.now(UTC) - timedelta(days=clips_older_than_days)

    clips_result = await session.execute(
        select(EvidenceClip.id, EvidenceClip.file_path).where(
            EvidenceClip.created_at < clips_cutoff, EvidenceClip.status == "sealed"
        )
    )
    clip_rows = clips_result.all()
    clip_paths = [path for _clip_id, path in clip_rows if path]
    clips_bytes_deleted = await asyncio.to_thread(_sum_existing_file_sizes, clip_paths)
    await asyncio.to_thread(_delete_existing_files, clip_paths)

    clip_ids = [clip_id for clip_id, _path in clip_rows]
    if clip_ids:
        await session.execute(delete(EvidenceClip).where(EvidenceClip.id.in_(clip_ids)))

    detections_result = await session.execute(
        delete(Detection).where(Detection.observed_at < detections_cutoff)
    )
    # AsyncSession.execute()'s stub return type is the generic Result[Any],
    # but for a Core DELETE statement the runtime object is genuinely a
    # CursorResult, which does have .rowcount — a real stub gap, not a
    # runtime risk.
    detections_deleted = detections_result.rowcount  # type: ignore[attr-defined]

    await record_audit_event(
        session,
        actor_email=actor_email,
        action="retention_executed",
        resource_type="retention_policy",
        detail={
            "detections_older_than_days": detections_older_than_days,
            "clips_older_than_days": clips_older_than_days,
            "detections_deleted": detections_deleted,
            "clips_deleted": len(clip_ids),
            "clips_bytes_deleted": clips_bytes_deleted,
        },
    )

    return RetentionExecutionResult(
        detections_deleted=detections_deleted,
        clips_deleted=len(clip_ids),
        clips_bytes_deleted=clips_bytes_deleted,
    )


async def check_integration_statuses() -> list[IntegrationStatusOut]:
    """Drives one representative lookup against each ExternalRegistry
    provider (docs/01-ARCHITECTURE.md §6.4) and reports whether the round
    trip genuinely succeeded — this is what lets the Admin Portal's
    Integrations tab say "Connected (mock)" honestly instead of asserting
    it. Every provider here runs against its own built-in mock transport
    (no real government credential exists in this deployment); swapping a
    provider to a real `base_url`/`api_key`/`transport` is the only change
    needed for this same check to report a real connection."""
    checks: list[tuple[str, str, str, str, Callable[[], Awaitable[object]]]] = [
        (
            "vahan",
            "VAHAN",
            "Vehicle registration lookups",
            "lookup_vehicle('GJ01AB1234')",
            lambda: VahanProvider().lookup_vehicle("GJ01AB1234"),
        ),
        (
            "sarthi",
            "SARTHI",
            "Driving licence lookups",
            "lookup_licence('GJ0120190001234')",
            lambda: SarthiProvider().lookup_licence("GJ0120190001234"),
        ),
        (
            "egujcop",
            "eGujCop",
            "FIR / case-record cross-reference",
            "lookup_person(full_name='Suresh Chauhan')",
            lambda: EGujCopProvider().lookup_person(PersonQuery(full_name="Suresh Chauhan")),
        ),
        (
            "afis",
            "AFIS",
            "Fingerprint/identity cross-reference",
            "lookup_person(photo_hash='sha256:af1s0001')",
            lambda: AfisProvider().lookup_person(PersonQuery(photo_hash="sha256:af1s0001")),
        ),
    ]

    statuses: list[IntegrationStatusOut] = []
    for provider_id, name, description, sample_operation, call in checks:
        started = time.monotonic()
        try:
            result = await call()
            latency_ms = (time.monotonic() - started) * 1000
            connected = True
            detail = (
                "Demonstration mock — the code path (auth, retry/circuit-breaker, rate "
                "limit, PII-redacted audit log) is real and round-tripped successfully "
                "just now; there is no live government credential behind it yet. See "
                "docs/07-DRIVER-SDK.md."
                if result
                else "Demonstration mock — round trip succeeded but the sample query "
                "had no match in the representative dataset."
            )
        except RegistryError as exc:
            latency_ms = (time.monotonic() - started) * 1000
            connected = False
            detail = f"Mock round trip failed: {exc}"
        statuses.append(
            IntegrationStatusOut(
                provider_id=provider_id,
                name=name,
                description=description,
                mode="mock",
                connected=connected,
                detail=detail,
                sample_operation=sample_operation,
                sample_latency_ms=round(latency_ms, 2),
                checked_at=datetime.now(UTC),
            )
        )
    return statuses


async def list_audit_log(session: AsyncSession, *, limit: int = 200) -> list[AuditLogEntry]:
    """Newest first — the Admin Portal's Audit log screen (docs/03-UX-
    DESIGN.md §6). `verify_chain` (core_api/audit/service.py) walks in the
    opposite (insertion) order since it must recompute forward from the
    genesis hash; this is purely a display query."""
    result = await session.execute(
        select(AuditLogEntry).order_by(AuditLogEntry.seq.desc()).limit(limit)
    )
    return list(result.scalars().all())
