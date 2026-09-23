"""Retention policy preview — docs/03-UX-DESIGN.md section 6: "per-data-class
retention sliders with a plain-language consequence preview (\"Event clips
will be deleted after 30 days. About 1.2 TB affected.\")".

This computes the preview against real counts (and, for sealed clips, real
file sizes already on disk) — nothing here is invented. Actually enforcing a
retention window (a scheduled deletion job) is a documented next step, not
built yet: this endpoint only ever reads.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.admin.schemas import IntegrationStatusOut
from core_api.db.models import Detection, EvidenceClip
from sentinel_core.gov_registry import (
    AfisProvider,
    EGujCopProvider,
    PersonQuery,
    RegistryError,
    SarthiProvider,
    VahanProvider,
)

__all__ = ["RetentionPreview", "check_integration_statuses", "preview_retention"]


class RetentionPreview:
    def __init__(self, *, detections_affected: int, clips_affected: int, clips_bytes_affected: int):
        self.detections_affected = detections_affected
        self.clips_affected = clips_affected
        self.clips_bytes_affected = clips_bytes_affected


def _sum_existing_file_sizes(paths: list[str]) -> int:
    total = 0
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file():
            total += path.stat().st_size
    return total


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
