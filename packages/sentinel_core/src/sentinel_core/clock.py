"""PTS-derived timing — the single source of truth for time in the platform.

ADR-005: frame arrival (wall-clock) time is *never* used for measurement. The
stream gateway replays a buffered group-of-pictures when a client attaches, so the
first one or two seconds of frames arrive faster than real time. Any tracker,
Kalman filter, speed estimate or route timeline driven by arrival time will
compute impossible velocities immediately after every reconnect.

Wall-clock is read exactly once per connection, to anchor the stream's PTS
origin to absolute time. Everything else is derived from presentation timestamps.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

__all__ = ["Frame", "FrameTiming", "StreamClock"]

# A backwards PTS jump, or a forward jump larger than this, is treated as a scene
# discontinuity: the recorded feeds loop, producing a hard cut like a camera reboot.
DISCONTINUITY_FORWARD_MS = 10_000.0
# Below this, a backwards jump is just B-frame reordering, not a loop point.
REORDER_TOLERANCE_MS = 250.0
# A gap longer than this is reported so motion models can widen their uncertainty.
GAP_THRESHOLD_MS = 1_000.0


@dataclass(frozen=True, slots=True)
class FrameTiming:
    """Timing metadata for a single decoded frame. Derived entirely from PTS."""

    camera_id: str
    pts_ms: float
    """Presentation timestamp, milliseconds from the start of the current stream leg."""
    seq: int
    """Monotonic frame counter for this connection, starting at 0."""
    stream_epoch: datetime
    """Absolute time corresponding to the current leg's PTS origin."""
    observed_at: datetime
    """stream_epoch + pts_ms. The authoritative timestamp for evidence."""
    delta_ms: float
    """Elapsed PTS since the previous frame. 0.0 for the first frame of a leg."""
    is_gap: bool
    """True when the inter-frame interval was unusually long (not a disconnect)."""
    is_discontinuity: bool
    """True on the first frame after a loop cut / scene change; reset long-lived state."""

    @property
    def delta_s(self) -> float:
        """Elapsed seconds since the previous frame, for motion models."""
        return self.delta_ms / 1000.0


@dataclass(frozen=True, slots=True)
class Frame[T]:
    """A decoded frame: timing plus a decoder-specific image payload.

    Generic over the image type so this package stays free of numpy/OpenCV.
    """

    timing: FrameTiming
    image: T
    width: int
    height: int

    @property
    def camera_id(self) -> str:
        return self.timing.camera_id

    @property
    def observed_at(self) -> datetime:
        return self.timing.observed_at


@dataclass(slots=True)
class StreamClock:
    """Converts a stream's presentation timestamps into absolute, monotonic time.

    One instance per camera connection. On reconnect or loop cut the clock
    re-anchors, so PTS restarting at zero does not rewind the evidence timeline.
    """

    camera_id: str
    fps_window: int = 60
    _epoch: datetime | None = field(default=None, init=False)
    _pts_origin_ms: float = field(default=0.0, init=False)
    _last_pts_ms: float | None = field(default=None, init=False)
    _max_pts_ms: float | None = field(default=None, init=False)
    _seq: int = field(default=0, init=False)
    _pts_history: deque[float] = field(init=False)
    _discontinuities: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._pts_history = deque(maxlen=self.fps_window)

    @property
    def discontinuities(self) -> int:
        """How many loop cuts / scene breaks this connection has survived."""
        return self._discontinuities

    @property
    def measured_fps(self) -> float | None:
        """Frame rate measured from PTS.

        Never trust the rate a decoder *declares* (OpenCV's CAP_PROP_FPS and its
        equivalents routinely disagree with the real delivery rate). Returns None
        until enough frames have been seen.
        """
        if len(self._pts_history) < 2:
            return None
        span_ms = self._pts_history[-1] - self._pts_history[0]
        if span_ms <= 0:
            return None
        return (len(self._pts_history) - 1) * 1000.0 / span_ms

    def observe(self, pts_ms: float, *, now: datetime | None = None) -> FrameTiming:
        """Register a frame's PTS and derive its timing.

        `now` is used only to anchor a new stream leg; it is never used to measure
        an interval. Callers should not pass it outside of tests.
        """
        if self._epoch is None:
            self._anchor(pts_ms, now)

        is_discontinuity = self._is_discontinuity(pts_ms)
        if is_discontinuity:
            self._discontinuities += 1
            # Keep the timeline moving forward across the cut: the new leg starts
            # where the old one ended, so evidence timestamps never go backwards.
            assert self._epoch is not None
            last_wall = self._to_wall(self._max_pts_ms or 0.0)
            self._epoch = last_wall
            self._pts_origin_ms = pts_ms
            self._pts_history.clear()

        delta_ms = 0.0
        if self._last_pts_ms is not None and not is_discontinuity:
            delta_ms = max(0.0, pts_ms - self._last_pts_ms)

        timing = FrameTiming(
            camera_id=self.camera_id,
            pts_ms=pts_ms,
            seq=self._seq,
            stream_epoch=self._epoch_or_raise(),
            observed_at=self._to_wall(pts_ms),
            delta_ms=delta_ms,
            is_gap=delta_ms > GAP_THRESHOLD_MS,
            is_discontinuity=is_discontinuity,
        )

        self._last_pts_ms = pts_ms
        self._max_pts_ms = pts_ms if is_discontinuity else max(self._max_pts_ms or pts_ms, pts_ms)
        self._seq += 1
        self._pts_history.append(pts_ms)
        return timing

    def reset(self) -> None:
        """Drop all state. Call on reconnect so the next frame re-anchors."""
        self._epoch = None
        self._pts_origin_ms = 0.0
        self._last_pts_ms = None
        self._max_pts_ms = None
        self._pts_history.clear()

    def _anchor(self, pts_ms: float, now: datetime | None) -> None:
        self._epoch = now or datetime.now(UTC)
        self._pts_origin_ms = pts_ms

    def _epoch_or_raise(self) -> datetime:
        if self._epoch is None:  # pragma: no cover - guarded by observe()
            raise RuntimeError("StreamClock used before anchoring")
        return self._epoch

    def _to_wall(self, pts_ms: float) -> datetime:
        return self._epoch_or_raise() + timedelta(milliseconds=pts_ms - self._pts_origin_ms)

    def _is_discontinuity(self, pts_ms: float) -> bool:
        if self._max_pts_ms is None:
            return False
        # Compare against the highest PTS seen, not the previous frame: with
        # B-frames the previous frame may itself be out of presentation order.
        if pts_ms < self._max_pts_ms - REORDER_TOLERANCE_MS:
            return True
        return pts_ms - self._max_pts_ms > DISCONTINUITY_FORWARD_MS
