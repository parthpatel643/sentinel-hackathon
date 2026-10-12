"""How long a reading has held, measured in footage by PTS.

The camera-condition checks (tamper.py, view_monitor.py) only change state
once a reading has held. "Held" is footage time, never a frame count: on
connect the gateway replays its buffered GOP faster than real time, and the
analysed rate varies by tier and camera, so N frames can be a tenth of a
second or ten seconds of footage (tests/test_compliance.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel_core.clock import REORDER_TOLERANCE_MS

__all__ = ["PtsStreak"]

# CAP_PROP_POS_MSEC comes from a 90 kHz timebase and is rarely a whole
# millisecond, so 8 fps can land a hair short of an exact 0.5 s.
_SLACK_MS = 0.5


@dataclass
class PtsStreak:
    """One run of agreeing readings. `extend()` with each agreeing reading's
    PTS, `reset()` when the reading changes, and `held()` asks whether the
    run is long enough.

    A run needs both a minimum duration of footage and a minimum number of
    readings: the duration so that a burst of frames close together in PTS
    (a replayed GOP, a 25 fps camera) is not mistaken for a sustained
    condition, and the count so that one frame, or two either side of a
    stretch we did not watch, is never enough on its own.
    """

    max_step_s: float
    """The most footage one step between readings can add. Longer gaps (a
    stall, a forward cut, checks skipped for want of detail) were not
    watched, so they cannot vouch for the condition holding."""

    _readings: int = field(default=0, init=False)
    _held_ms: float = field(default=0.0, init=False)
    _last_ms: float | None = field(default=None, init=False)

    @property
    def readings(self) -> int:
        return self._readings

    @property
    def held_s(self) -> float:
        return self._held_ms / 1000.0

    def reset(self) -> None:
        self._readings = 0
        self._held_ms = 0.0
        self._last_ms = None

    def extend(self, pts_ms: float) -> None:
        last = self._last_ms
        if last is None or pts_ms < last - REORDER_TOLERANCE_MS:
            # The first reading, or PTS jumped back (a reconnect or a loop
            # restarts it): footage on the old timeline cannot be added to
            # footage on the new one, so the run starts again here.
            self._readings, self._held_ms, self._last_ms = 1, 0.0, pts_ms
            return
        if pts_ms <= last:
            # The same instant again (a repeated or reordered frame): no new
            # footage, and not a further reading of the scene.
            return
        self._held_ms += min(pts_ms - last, self.max_step_s * 1000.0)
        self._readings += 1
        self._last_ms = pts_ms

    def held(self, min_s: float, min_readings: int) -> bool:
        return self._readings >= min_readings and self._held_ms + _SLACK_MS >= min_s * 1000.0
