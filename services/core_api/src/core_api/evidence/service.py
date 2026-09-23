"""Event-clip recording + sealing — docs/01-ARCHITECTURE.md section 6.5's
"on alert, a sealed pre/post-roll clip" and docs/05-DELIVERY-PLAN.md M7's
exit criterion: "click an alert -> watch the sealed clip".

Recording is off by default (infra/compose/mediamtx.yml) — Model 4 is
event-driven, not a statewide archive. Sealing a clip therefore means: turn
recording on, wait out a fixed post-roll window, turn it back off, then
locate, concatenate, hash and persist whatever MediaMTX actually wrote to
disk in that window. There is no true PRE-roll here (footage from before the
alert) since nothing was recording before the request — that would need an
always-on rolling buffer, a materially different (and more expensive)
design this milestone does not implement; the alert's own detection
snapshot remains the only "before" artefact until that's built.

Only cameras relayed through our own local dev/* MediaMTX instance can be
*sealed* today: `_patch_dev_relay_recording` toggles `record` on the single
dev/* path pattern configured in mediamtx.yml, and nothing else. This is
narrower than live *preview*, which `registry.service.resolve_camera_stream`
now also solves for external (gov-catalogue) cameras by proxying them
through an on-demand `ext/*` relay path — but recording that same on-demand
path is a separate, still-unimplemented feature: it would need per-path
(not path-pattern) record toggling, since external cameras don't share one
static path the way the whole synthetic grid does.
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core_api.db.models import Alert, EvidenceClip
from sentinel_core.config import Settings

__all__ = ["get_clip_for_alert", "request_seal_clip", "seal_clip_task"]


async def _patch_dev_relay_recording(settings: Settings, *, record: bool) -> None:
    """Toggle recording on the whole dev/* path pattern. Not per-camera:
    mediamtx.yml only defines one wildcard path entry for the entire
    synthetic grid today, so this is the only patch target that exists."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        await client.patch(
            f"{settings.relay_api_url}/v3/config/paths/patch/{settings.evidence_dev_relay_path_pattern}",
            json={"record": record},
        )


def _camera_recording_dir(settings: Settings, camera_id: str) -> Path:
    # scripts/synthetic_grid.py publishes to dev/<camera_id>, and mediamtx.yml's
    # recordPath template is /recordings/%path/... — this must match that
    # path segment exactly.
    return Path(settings.recordings_dir) / "dev" / camera_id


def _probe_duration_s(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


class _SealResult:
    """Plain result-carrier for the blocking half of sealing (file discovery,
    concat, hashing) — kept separate from the async orchestration below so
    that entire step can run in one `asyncio.to_thread` call instead of a
    blocking subprocess/filesystem call sitting directly in an async def
    (flake8-async's ASYNC221/ASYNC240, which would otherwise flag exactly
    that)."""

    def __init__(
        self,
        *,
        file_path: Path | None,
        sha256: str | None,
        duration_s: float | None,
        error: str | None,
    ):
        self.file_path = file_path
        self.sha256 = sha256
        self.duration_s = duration_s
        self.error = error


def _seal_from_segments(
    recordings_dir: Path,
    existing_before: set[Path],
    window_start: float,
    sealed_dir: Path,
    clip_id: uuid.UUID,
) -> _SealResult:
    """The entire blocking half of sealing a clip: find the segments MediaMTX
    wrote during the seal window, concatenate them (or just copy the one
    segment, if there's only one) with ffmpeg, and hash the result. Runs
    off the event loop via asyncio.to_thread — see _SealResult."""
    if not recordings_dir.exists():
        return _SealResult(
            file_path=None,
            sha256=None,
            duration_s=None,
            error=f"No recordings directory for camera at {recordings_dir}.",
        )

    segments = sorted(
        (
            p
            for p in recordings_dir.glob("*.mp4")
            if p not in existing_before or p.stat().st_mtime >= window_start
        ),
        key=lambda p: p.stat().st_mtime,
    )
    if not segments:
        return _SealResult(
            file_path=None,
            sha256=None,
            duration_s=None,
            error="No recording segments were produced in the seal window.",
        )

    sealed_dir.mkdir(parents=True, exist_ok=True)
    output_path = sealed_dir / f"{clip_id}.mp4"

    if len(segments) == 1:
        output_path.write_bytes(segments[0].read_bytes())
    else:
        concat_list = sealed_dir / f"{clip_id}.concat.txt"
        concat_list.write_text("\n".join(f"file '{p.resolve()}'" for p in segments))
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        concat_list.unlink(missing_ok=True)
        if result.returncode != 0:
            return _SealResult(
                file_path=None,
                sha256=None,
                duration_s=None,
                error=f"ffmpeg concat failed: {result.stderr[-500:]}",
            )

    sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
    duration_s = _probe_duration_s(output_path)
    return _SealResult(file_path=output_path, sha256=sha256, duration_s=duration_s, error=None)


async def request_seal_clip(session: AsyncSession, alert: Alert) -> EvidenceClip:
    """Creates the pending row. The actual recording/concat/hash work runs
    afterwards in seal_clip_task (a FastAPI BackgroundTask), so the HTTP
    response isn't held open for the whole post-roll window."""
    clip = EvidenceClip(alert_id=alert.id, camera_id=alert.camera_id, status="pending")
    session.add(clip)
    await session.flush()
    await session.commit()
    await session.refresh(clip)
    return clip


async def get_clip_for_alert(session: AsyncSession, alert_id: uuid.UUID) -> EvidenceClip | None:
    result = await session.execute(
        select(EvidenceClip)
        .where(EvidenceClip.alert_id == alert_id)
        .order_by(EvidenceClip.created_at.desc())
    )
    return result.scalars().first()


async def _mark_failed(session: AsyncSession, clip_id: uuid.UUID, error: str) -> None:
    clip = await session.get(EvidenceClip, clip_id)
    if clip is None:
        return
    clip.status = "failed"
    clip.error = error[:2000]
    await session.commit()


async def seal_clip_task(
    clip_id: uuid.UUID,
    camera_id: str,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Runs in the background after the seal-clip endpoint has already
    responded. Opens its own DB session since the request's session is
    closed by the time this runs."""
    recordings_dir = _camera_recording_dir(settings, camera_id)
    existing_before = await asyncio.to_thread(
        lambda: set(recordings_dir.glob("*.mp4")) if recordings_dir.exists() else set()
    )
    window_start = time.time()

    async with session_factory() as session:
        try:
            await _patch_dev_relay_recording(settings, record=True)
            await asyncio.sleep(settings.evidence_post_roll_s)
            await _patch_dev_relay_recording(settings, record=False)
            # MediaMTX needs a moment to flush and close the in-progress
            # segment file after the config patch takes effect.
            await asyncio.sleep(2.0)

            sealed_dir = Path(settings.recordings_dir) / "sealed"
            seal_result = await asyncio.to_thread(
                _seal_from_segments,
                recordings_dir,
                existing_before,
                window_start,
                sealed_dir,
                clip_id,
            )
            if (
                seal_result.error is not None
                or seal_result.file_path is None
                or seal_result.sha256 is None
            ):
                await _mark_failed(
                    session, clip_id, seal_result.error or "Sealing failed for an unknown reason."
                )
                return

            sealed_at = datetime.now(UTC)
            manifest: dict[str, object] = {
                "clip_id": str(clip_id),
                "camera_id": camera_id,
                "sealed_at": sealed_at.isoformat(),
                "sha256": seal_result.sha256,
                "duration_s": seal_result.duration_s,
                "note": (
                    "Recording started when this seal was requested, not before — see "
                    "evidence/service.py's module docstring on why there is no true pre-roll yet."
                ),
            }

            clip = await session.get(EvidenceClip, clip_id)
            if clip is None:
                return
            clip.status = "sealed"
            clip.file_path = str(seal_result.file_path)
            clip.sha256 = seal_result.sha256
            clip.manifest = manifest
            clip.duration_s = seal_result.duration_s
            clip.sealed_at = sealed_at
            await session.commit()
        except Exception as exc:
            await _mark_failed(session, clip_id, str(exc))
