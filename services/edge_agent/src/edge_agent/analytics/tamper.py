"""Camera tamper detection — M13 secondary analytics: docs/05-DELIVERY-
PLAN.md's "camera tamper detection." Pure frame-statistics heuristics, no
model weights: a covered/blinded lens collapses a frame's local contrast
to near-zero; a genuinely blurred (defocused, or physically smudged) lens
collapses high-frequency detail specifically.

A moved or re-aimed camera is `ViewMonitor`'s to judge (view_monitor.py): it
compares the scene's fixed structure geometrically, where this detector's
earlier brightness-difference check caught up with a moved view within a
second or two and was easily set off by a large vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from edge_agent.analytics.pts_streak import PtsStreak

__all__ = ["TamperDetector", "TamperStatus"]

TamperStatus = str  # "ok" | "covered" | "blurred"


@dataclass
class TamperDetector:
    """One instance per camera. Feed it grayscale-convertible frames in
    order, each with its PTS; `update()` returns the current tamper status,
    which only changes once a reading has held for `sustained_s` of footage
    over at least `min_readings` frames — a single noisy frame (a truck
    momentarily filling the frame, a compression artifact) must not flip
    camera-wide status, and neither may a burst of frames delivered close
    together in PTS. Timing is the stream's PTS only, never arrival time."""

    covered_brightness_threshold: float = 15.0
    blur_variance_threshold: float = 20.0
    sustained_s: float = 0.5
    """Footage a reading must hold for: five frames at the 8 fps analysis
    rate (scheduler `sampled_fps`), which was the old frame count."""
    min_readings: int = 3
    """Frames that must agree, however long they span."""
    max_step_s: float = 0.25
    """The most footage one interval between frames adds: the slowest rate
    the scheduler decodes at (motion-gated idle, 4 fps). Across a longer gap
    nothing was watched, so it cannot vouch for the reading holding."""

    _candidate_status: TamperStatus = "ok"
    _streak: PtsStreak = field(init=False)
    _current_status: TamperStatus = "ok"

    def __post_init__(self) -> None:
        self._streak = PtsStreak(max_step_s=self.max_step_s)

    def update(self, frame: np.ndarray, *, pts_ms: float) -> TamperStatus:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        reading = self._classify(gray)

        if reading != self._candidate_status:
            self._candidate_status = reading
            self._streak.reset()
        self._streak.extend(pts_ms)

        if self._streak.held(self.sustained_s, self.min_readings):
            self._current_status = self._candidate_status
        return self._current_status

    def reset_timing(self) -> None:
        """The stream's PTS origin moved (reconnect, loop cut). The status
        stands — the lens did not change — but a reading in progress must
        start its run again on the new timeline."""
        self._streak.reset()

    @property
    def current_status(self) -> TamperStatus:
        return self._current_status

    def _classify(self, gray: np.ndarray) -> TamperStatus:
        mean_brightness = float(np.mean(gray))
        if mean_brightness < self.covered_brightness_threshold:
            return "covered"

        # Laplacian variance — the standard, well-established "how much
        # high-frequency detail is present" focus/blur measure.
        focus_measure = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if focus_measure < self.blur_variance_threshold:
            return "blurred"
        return "ok"
