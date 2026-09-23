"""Writes the two artefacts every ANPR event's `EvidenceRef.snapshot_uri`
points at: a face-blurred snapshot (the default, served-by-core_api
version) and its unblurred original (written to a separate directory only
the reveal workflow reads — never served directly). See face_blur.py and
docs/08-SECURITY-HARDENING.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from edge_agent.analytics.face_blur import blur_faces

__all__ = ["SnapshotWriter"]

logger = logging.getLogger(__name__)


class SnapshotWriter:
    """`blurred_dir` is what `snapshot_uri` refers to (and what core_api's
    snapshot endpoint serves by default); `originals_dir` is a separate
    directory the reveal-on-authorisation workflow reads from — never
    exposed by any "just serve this file" route. Both directories are
    expected to be the same host paths core_api's `snapshots_dir`/
    `snapshot_originals_dir` settings point at (this dev deployment shares
    a filesystem between edge and core, the same bind-mount pattern M7's
    evidence-clip recording already established).

    `blur_fn` defaults to the real DNN-backed `blur_faces` but is
    injectable — tests use a fake that doesn't need the real model
    downloaded, the same seam `AnprPipeline` already uses for its
    detector/reader ports."""

    def __init__(
        self,
        *,
        blurred_dir: Path,
        originals_dir: Path,
        blur_fn: Callable[[np.ndarray], np.ndarray] = blur_faces,
    ):
        self._blurred_dir = blurred_dir
        self._originals_dir = originals_dir
        self._blur_fn = blur_fn
        self._blurred_dir.mkdir(parents=True, exist_ok=True)
        self._originals_dir.mkdir(parents=True, exist_ok=True)

    def write(self, event_id: str, frame_image: np.ndarray) -> str:
        """Returns the `snapshot_uri` to embed in the event's `EvidenceRef`
        — an opaque `snapshot://<event_id>` marker, not a raw filesystem
        path: core_api resolves it against its own configured directory by
        convention (the event_id), the same reasoning M7's evidence clips
        already established for not leaking host paths onto the wire."""
        try:
            blurred = self._blur_fn(frame_image)
        except Exception:
            # A face-detector failure must never block the ANPR event
            # itself from being emitted — but it also must never fall back
            # to saving the UNBLURRED frame as if it were the safe default.
            # Better to have no snapshot at all than a silently-unblurred
            # one.
            logger.exception("face blur failed for event %s; no snapshot written", event_id)
            return ""

        blurred_path = self._blurred_dir / f"{event_id}.jpg"
        original_path = self._originals_dir / f"{event_id}.jpg"
        cv2.imwrite(str(blurred_path), blurred)
        cv2.imwrite(str(original_path), frame_image)
        return f"snapshot://{event_id}"
