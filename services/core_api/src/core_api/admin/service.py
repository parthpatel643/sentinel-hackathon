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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Detection, EvidenceClip

__all__ = ["RetentionPreview", "preview_retention"]


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
