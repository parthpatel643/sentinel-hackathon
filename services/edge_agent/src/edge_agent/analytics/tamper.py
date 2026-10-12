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

from dataclasses import dataclass

import cv2
import numpy as np

__all__ = ["TamperDetector", "TamperStatus"]

TamperStatus = str  # "ok" | "covered" | "blurred"


@dataclass
class TamperDetector:
    """One instance per camera. Feed it grayscale-convertible frames in
    order; `update()` returns the current tamper status, which only
    changes after `consecutive_frames_required` consistent readings in a
    row — a single noisy frame (a truck momentarily filling the frame,
    a compression artifact) must not flip camera-wide status."""

    covered_brightness_threshold: float = 15.0
    blur_variance_threshold: float = 20.0
    consecutive_frames_required: int = 5

    _candidate_status: TamperStatus = "ok"
    _candidate_streak: int = 0
    _current_status: TamperStatus = "ok"

    def update(self, frame: np.ndarray) -> TamperStatus:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        reading = self._classify(gray)

        if reading == self._candidate_status:
            self._candidate_streak += 1
        else:
            self._candidate_status = reading
            self._candidate_streak = 1

        if self._candidate_streak >= self.consecutive_frames_required:
            self._current_status = self._candidate_status
        return self._current_status

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
