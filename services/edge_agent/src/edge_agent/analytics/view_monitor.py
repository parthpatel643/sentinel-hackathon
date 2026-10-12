"""Camera view monitoring: notice when a camera no longer points where it did.

A camera knocked by wind or a vehicle, turned by someone who does not want to
be filmed, or slipping on its mount stops covering the road it was installed
for — and nothing in the video stream says so. This learns each camera's
normal view and checks, every couple of seconds of footage, whether the
current view still lines up with it.

How the comparison works: ORB keypoints are found on the fixed structure of
the scene (buildings, poles, kerbs, road markings) in the remembered view and
in the current one, matched, and fitted to a rotation-translation-scale
transform with RANSAC. Moving traffic and pedestrians are a minority of
keypoints and fall out as outliers, so they never look like a camera move;
CLAHE before detection keeps matching steady through haze, rain and changing
light.

Three outcomes are reported, each only after it has held for several checks:

- **shifted** — the view still matches, but displaced, rotated or zoomed: the
  camera physically moved. Confirmed in seconds.
- **unrecognised** — the view no longer matches at all, though the frame is
  neither dark nor blank (those are `TamperDetector`'s covered/blurred): the
  camera was turned to something else, something is in front of it, or
  weather has hidden the scene. Confirmed only after a sustained period,
  because heavy rain or a parked bus can also do this for a while.
- **restored** — the view lines up with the remembered one again.

The remembered view is refreshed now and then while the camera is confirmed
in place, so gradual change — dusk, shadows, seasons — is followed rather than
mistaken for a move. It is never refreshed from a view that does not line up,
so a moved camera cannot quietly become the new normal; after a long hold the
new view is adopted, so a camera repositioned on purpose stops reporting, and
the alert already raised stays on record for an operator to close.

Time comes from the stream's PTS, never the wall clock (ADR-005).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, cast

import cv2
import numpy as np

__all__ = ["ViewChange", "ViewMonitor", "ViewStatus"]

ViewStatus = Literal["learning", "ok", "moved", "view_lost"]
ChangeKind = Literal["shifted", "unrecognised", "restored"]


@dataclass(frozen=True)
class ViewChange:
    kind: ChangeKind
    pts_ms: float
    shift_pct: float | None
    """Displacement of the view, as a percentage of the frame width."""
    rotation_deg: float | None
    scale: float | None
    match_ratio: float
    """Matched fixed points as a share of those in the remembered view."""
    reference: np.ndarray
    """The remembered (before) view, full resolution."""
    current: np.ndarray
    """The view now (after), full resolution."""


@dataclass(frozen=True)
class _Snapshot:
    image: np.ndarray
    keypoints: tuple[cv2.KeyPoint, ...]
    descriptors: np.ndarray
    pts_ms: float
    size: tuple[int, int]
    """(width, height) of the working image the keypoints were found on."""


@dataclass(frozen=True)
class _Alignment:
    inliers: int
    shift_frac: float
    rotation_deg: float
    scale: float
    match_ratio: float


@dataclass
class ViewMonitor:
    """One per camera. Call `observe()` with every decoded frame; it checks
    at most once per `check_interval_s` of stream time and returns a
    `ViewChange` when a change is confirmed or the view returns."""

    check_interval_s: float = 2.0
    work_width: int = 480
    min_features: int = 60
    """Below this the frame has too little structure to judge (night with no
    lighting, a covered lens): the check is skipped, not counted."""
    min_inliers: int = 18
    aligned_shift: float = 0.02
    aligned_rotation_deg: float = 1.5
    aligned_scale: float = 0.04
    moved_shift: float = 0.06
    moved_rotation_deg: float = 4.0
    moved_scale: float = 0.10
    learn_checks: int = 3
    confirm_checks: int = 3
    """Consecutive shifted checks before reporting (≈6 s at 2 s a check)."""
    unrecognised_checks: int = 30
    """Consecutive unmatched checks before reporting (≈60 s)."""
    restore_checks: int = 3
    refresh_s: float = 120.0
    """While aligned, re-anchor the remembered view this often."""
    adopt_after_s: float = 900.0
    """After a confirmed change, adopt the new view once it has held this long."""

    _reference: _Snapshot | None = field(default=None, init=False)
    _candidate: _Snapshot | None = field(default=None, init=False)
    _candidate_agreements: int = field(default=0, init=False)
    _next_check_ms: float | None = field(default=None, init=False)
    _status: ViewStatus = field(default="learning", init=False)
    _shifted_streak: int = field(default=0, init=False)
    _unrecognised_streak: int = field(default=0, init=False)
    _restore_streak: int = field(default=0, init=False)
    _last_refresh_ms: float = field(default=0.0, init=False)
    _changed_at_ms: float | None = field(default=None, init=False)
    features: int = 1500
    """ORB keypoints per check. More finds more of the fixed structure at
    night, when moving headlights take a large share of the strongest points."""
    _orb: cv2.ORB = field(init=False)
    _clahe: cv2.CLAHE = field(
        default_factory=lambda: cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)), init=False
    )
    _matcher: cv2.BFMatcher = field(
        default_factory=lambda: cv2.BFMatcher(cv2.NORM_HAMMING), init=False
    )

    def __post_init__(self) -> None:
        self._orb = cv2.ORB.create(nfeatures=self.features)

    @property
    def status(self) -> ViewStatus:
        return self._status

    def reset_timing(self) -> None:
        """The stream's PTS origin moved (reconnect, loop point). The
        remembered view is kept — the camera did not move — only the check
        clock restarts."""
        self._next_check_ms = None

    def observe(self, frame: np.ndarray, *, pts_ms: float) -> ViewChange | None:
        if self._next_check_ms is not None and pts_ms < self._next_check_ms:
            return None
        self._next_check_ms = pts_ms + self.check_interval_s * 1000.0
        snapshot = self._describe(frame, pts_ms)
        if snapshot is None:
            return None
        if self._reference is None:
            self._learn(snapshot)
            return None
        alignment = self._align(self._reference, snapshot)
        if self._status in ("moved", "view_lost"):
            return self._while_changed(snapshot, alignment)
        return self._while_ok(snapshot, alignment)

    # --- states -------------------------------------------------------------

    def _learn(self, snapshot: _Snapshot) -> None:
        if self._candidate is None:
            self._candidate = snapshot
            self._candidate_agreements = 0
            return
        alignment = self._align(self._candidate, snapshot)
        if alignment is not None and self._is_aligned(alignment):
            self._candidate_agreements += 1
            if self._candidate_agreements >= self.learn_checks - 1:
                self._reference = self._candidate
                self._last_refresh_ms = snapshot.pts_ms
                self._status = "ok"
                self._candidate = None
        else:
            self._candidate = snapshot
            self._candidate_agreements = 0

    def _while_ok(self, snapshot: _Snapshot, alignment: _Alignment | None) -> ViewChange | None:
        assert self._reference is not None
        if alignment is not None and self._is_aligned(alignment):
            self._shifted_streak = 0
            self._unrecognised_streak = 0
            if snapshot.pts_ms - self._last_refresh_ms >= self.refresh_s * 1000.0:
                self._reference = snapshot
                self._last_refresh_ms = snapshot.pts_ms
            return None
        if alignment is not None and self._is_moved(alignment):
            self._shifted_streak += 1
            self._unrecognised_streak = 0
            if self._shifted_streak >= self.confirm_checks:
                return self._change("shifted", "moved", snapshot, alignment)
            return None
        if alignment is None:
            self._unrecognised_streak += 1
            self._shifted_streak = 0
            if self._unrecognised_streak >= self.unrecognised_checks:
                return self._change("unrecognised", "view_lost", snapshot, None)
            return None
        # Matched, but between "in place" and "moved": not evidence either way.
        return None

    def _while_changed(
        self, snapshot: _Snapshot, alignment: _Alignment | None
    ) -> ViewChange | None:
        assert self._reference is not None and self._changed_at_ms is not None
        if alignment is not None and self._is_aligned(alignment):
            self._restore_streak += 1
            if self._restore_streak >= self.restore_checks:
                change = self._event("restored", snapshot, alignment)
                self._status = "ok"
                self._changed_at_ms = None
                self._restore_streak = 0
                self._last_refresh_ms = snapshot.pts_ms
                return change
            return None
        self._restore_streak = 0
        if snapshot.pts_ms - self._changed_at_ms >= self.adopt_after_s * 1000.0:
            # Held long enough to be the camera's new normal: stop reporting it.
            # The alert raised at the time stays open for an operator.
            self._reference = None
            self._candidate = snapshot
            self._candidate_agreements = 0
            self._status = "learning"
            self._changed_at_ms = None
        return None

    def _change(
        self,
        kind: ChangeKind,
        status: ViewStatus,
        snapshot: _Snapshot,
        alignment: _Alignment | None,
    ) -> ViewChange:
        change = self._event(kind, snapshot, alignment)
        self._status = status
        self._changed_at_ms = snapshot.pts_ms
        self._shifted_streak = 0
        self._unrecognised_streak = 0
        self._restore_streak = 0
        return change

    def _event(
        self, kind: ChangeKind, snapshot: _Snapshot, alignment: _Alignment | None
    ) -> ViewChange:
        assert self._reference is not None
        return ViewChange(
            kind=kind,
            pts_ms=snapshot.pts_ms,
            shift_pct=round(alignment.shift_frac * 100, 1) if alignment else None,
            rotation_deg=round(alignment.rotation_deg, 1) if alignment else None,
            scale=round(alignment.scale, 3) if alignment else None,
            match_ratio=round(alignment.match_ratio, 3) if alignment else 0.0,
            reference=self._reference.image,
            current=snapshot.image,
        )

    # --- geometry -----------------------------------------------------------

    def _is_aligned(self, a: _Alignment) -> bool:
        return (
            a.shift_frac < self.aligned_shift
            and abs(a.rotation_deg) < self.aligned_rotation_deg
            and abs(a.scale - 1.0) < self.aligned_scale
        )

    def _is_moved(self, a: _Alignment) -> bool:
        return (
            a.shift_frac >= self.moved_shift
            or abs(a.rotation_deg) >= self.moved_rotation_deg
            or abs(a.scale - 1.0) >= self.moved_scale
        )

    def _describe(self, frame: np.ndarray, pts_ms: float) -> _Snapshot | None:
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        height, width = grey.shape[:2]
        if width > self.work_width:
            grey = cv2.resize(
                grey,
                (self.work_width, round(height * self.work_width / width)),
                interpolation=cv2.INTER_AREA,
            )
        grey = self._clahe.apply(grey)
        keypoints, descriptors = self._orb.detectAndCompute(grey, None)
        if descriptors is None or len(keypoints) < self.min_features:
            return None
        return _Snapshot(
            frame.copy(), tuple(keypoints), descriptors, pts_ms, (grey.shape[1], grey.shape[0])
        )

    def _align(self, reference: _Snapshot, current: _Snapshot) -> _Alignment | None:
        """The transform carrying the remembered view onto the current one,
        or None when too few fixed points match to say."""
        pairs = self._matcher.knnMatch(reference.descriptors, current.descriptors, k=2)
        good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
        if len(good) < self.min_inliers:
            return None
        src = np.array([reference.keypoints[m.queryIdx].pt for m in good], dtype=np.float32)
        dst = np.array([current.keypoints[m.trainIdx].pt for m in good], dtype=np.float32)
        # The stubs promise arrays, but OpenCV returns None when no transform fits.
        matrix, mask = cast(
            tuple[np.ndarray | None, np.ndarray | None],
            cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0),
        )
        if matrix is None or mask is None:
            return None
        inliers = int(mask.sum())
        if inliers < self.min_inliers:
            return None
        a, b, tx = float(matrix[0, 0]), float(matrix[1, 0]), float(matrix[0, 2])
        ty = float(matrix[1, 2])
        scale = math.hypot(a, b)
        rotation = math.degrees(math.atan2(b, a))
        # Translation of the frame centre, so a pure rotation or zoom about
        # the centre does not read as a shift.
        width, height = reference.size
        cx, cy = width / 2, height / 2
        moved_x = a * cx - b * cy + tx - cx
        moved_y = b * cx + a * cy + ty - cy
        return _Alignment(
            inliers=inliers,
            shift_frac=math.hypot(moved_x, moved_y) / width,
            rotation_deg=rotation,
            scale=scale,
            match_ratio=inliers / max(1, len(reference.keypoints)),
        )
