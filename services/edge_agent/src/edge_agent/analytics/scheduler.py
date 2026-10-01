"""Decides which frames each camera spends inference on, by analytics tier.

Vehicle and plate detection is the dominant cost of the edge worker: four
1080p cameras analysed at their full 25 fps saturate an 8-core laptop
(evidence/M1-CAPACITY-FINDINGS.md). A statewide estate cannot afford to
analyse every frame of every camera, and a vehicle crossing a junction stays
in shot for one to three seconds, so it does not need to. The tier stored on
each camera in the registry (docs/04-SCALE-PLAN.md's tiering table) decides:

- `a_continuous` — every frame, or every `stride`-th: priority junctions.
- `b_sampled` — a fixed analysis rate (`sampled_fps`), paced by PTS, however
  fast the camera streams: the default for most cameras.
- `c_motion_gated` — a cheap motion check at `motion_check_fps`; analysis at
  `sampled_fps` only while something moves, and for `motion_hold_s` after.
  For quiet scenes: a depot gate at night, a PDS godown.
- `d_registry_only` — never opened (filtered out before a pipeline exists).

All pacing uses the stream's own presentation timestamps, never the wall
clock (tests/test_compliance.py): a frame's position in the stream says how
far apart two frames are; when they happened to be read does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from sentinel_core.clock import Frame, FrameTiming
from sentinel_core.schemas import AnalyticsTier

__all__ = ["AnalysisScheduler", "SchedulerConfig"]

_MOTION_WIDTH = 160
_PIXEL_DELTA = 25


@dataclass(slots=True, frozen=True)
class SchedulerConfig:
    stride: int = 1
    sampled_fps: float = 8.0
    """Eight analysed frames a second keeps several reads of every vehicle for
    the plate voter, at about a third of a 25 fps camera's full cost."""
    motion_check_fps: float = 4.0
    motion_hold_s: float = 3.0
    motion_threshold: float = 0.01
    """Fraction of a downscaled frame whose brightness must change for it to
    count as motion — a car across a lane, not sensor noise or a flag."""


@dataclass(slots=True)
class AnalysisScheduler:
    tier: AnalyticsTier
    config: SchedulerConfig = field(default_factory=SchedulerConfig)
    _frames_seen: int = field(default=0, init=False)
    _next_due_pts: float | None = field(default=None, init=False)
    _previous: np.ndarray | None = field(default=None, init=False)
    _motion_until_pts: float | None = field(default=None, init=False)

    def should_decode(self, timing: FrameTiming) -> bool:
        """Whether this frame should be turned into an image at all."""
        if timing.seq == 0 or timing.is_discontinuity:
            # A new connection or a loop cut: PTS restarts, and the motion
            # baseline belongs to a scene that no longer exists.
            self._reset()
        if self.tier is AnalyticsTier.A_CONTINUOUS:
            self._frames_seen += 1
            return (self._frames_seen - 1) % max(1, self.config.stride) == 0
        rate = self.config.sampled_fps
        if self.tier is AnalyticsTier.C_MOTION_GATED and not self._in_motion(timing.pts_ms):
            rate = self.config.motion_check_fps
        return self._due(timing.pts_ms, rate)

    def should_analyse(self, frame: Frame[np.ndarray]) -> bool:
        """Whether a decoded frame is worth vehicle and plate detection."""
        if self.tier is not AnalyticsTier.C_MOTION_GATED:
            return True
        small = _downscaled_gray(frame.image)
        previous, self._previous = self._previous, small
        if previous is not None and previous.shape == small.shape:
            changed = np.count_nonzero(cv2.absdiff(small, previous) > _PIXEL_DELTA)
            if changed / small.size >= self.config.motion_threshold:
                self._motion_until_pts = frame.timing.pts_ms + self.config.motion_hold_s * 1000
        return self._in_motion(frame.timing.pts_ms)

    def _due(self, pts_ms: float, rate_fps: float) -> bool:
        """An accumulating schedule: each due time is the previous due time
        plus one interval, not the last decoded frame plus one, so frames
        landing just after their slot do not drift the average rate."""
        interval_ms = 1000.0 / rate_fps
        due = self._next_due_pts
        if due is None or pts_ms + interval_ms < due:
            # First frame, or the schedule is ahead of the stream (the rate
            # just dropped, from motion back to idle checks): start afresh.
            self._next_due_pts = pts_ms + interval_ms
            return True
        if pts_ms + 0.5 < due:
            return False
        next_due = due + interval_ms
        # After a gap the slot is already behind the stream: resume one
        # interval from this frame rather than firing on every catch-up frame.
        self._next_due_pts = next_due if next_due > pts_ms else pts_ms + interval_ms
        return True

    def _in_motion(self, pts_ms: float) -> bool:
        return self._motion_until_pts is not None and pts_ms <= self._motion_until_pts

    def _reset(self) -> None:
        self._frames_seen = 0
        self._next_due_pts = None
        self._previous = None
        self._motion_until_pts = None


def _downscaled_gray(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    scale = _MOTION_WIDTH / max(1, width)
    small = cv2.resize(image, (_MOTION_WIDTH, max(1, int(height * scale))))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
