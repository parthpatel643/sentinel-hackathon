"""Camera tamper detection — M13 secondary analytics: docs/05-DELIVERY-
PLAN.md's "camera tamper detection." Pure frame-statistics heuristics, no
model weights: a covered/blinded lens collapses a frame's local contrast
to near-zero; a genuinely blurred (defocused, or physically smudged) lens
collapses high-frequency detail specifically; a moved/reoriented camera
produces a large, sustained shift in the scene's own reference frame that
a running background average doesn't already explain (unlike ordinary
motion, e.g. a passing vehicle, which is a small fraction of the frame and
resolves within a few frames).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

__all__ = ["TamperDetector", "TamperStatus"]

TamperStatus = str  # "ok" | "covered" | "blurred" | "moved"


@dataclass
class TamperDetector:
    """One instance per camera. Feed it grayscale-convertible frames in
    order; `update()` returns the current tamper status, which only
    changes after `consecutive_frames_required` consistent readings in a
    row — a single noisy frame (a truck momentarily filling the frame,
    a compression artifact) must not flip camera-wide status."""

    covered_brightness_threshold: float = 15.0
    blur_variance_threshold: float = 20.0
    moved_diff_threshold: float = 45.0
    consecutive_frames_required: int = 5

    _reference: np.ndarray | None = None
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

        # The reference frame for "moved" detection is a slow exponential
        # average, not the previous raw frame — that would flag every
        # passing vehicle as camera movement.
        gray_f = gray.astype(np.float32)
        self._reference = (
            gray_f if self._reference is None else 0.95 * self._reference + 0.05 * gray_f
        )
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

        if self._reference is not None:
            diff = float(np.mean(np.abs(gray.astype(np.float32) - self._reference)))
            if diff > self.moved_diff_threshold:
                return "moved"

        return "ok"
