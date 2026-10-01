"""Per-camera reconnect supervisor.

Owns exactly one camera's lifecycle: open, read until something goes wrong,
reconnect with exponential backoff. This is where the organisers' resilience
rules actually live — a capture that opens once and dies on the first hiccup
would fail the very first evaluation run.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

import numpy as np

from edge_agent.pipeline.capture import CaptureConfig, RtspCapture
from sentinel_core.clock import Frame, FrameTiming
from sentinel_core.schemas import CameraStatus

__all__ = ["CameraSupervisor", "SupervisorConfig"]

logger = logging.getLogger(__name__)

# Frames grabbed per worker-thread hop while the scheduler skips them: enough
# to make skipping cheap, few enough that a stop is still noticed promptly.
_MAX_GRABS_PER_HOP = 64


class _Skipped:
    """Frames were read and timed, none was selected for analysis."""


_SKIPPED = _Skipped()


@dataclass(slots=True)
class SupervisorConfig:
    initial_backoff_s: float = 2.0
    max_backoff_s: float = 30.0
    """'Start at ~2s, cap at ~30s' — the organisers' own numbers."""
    backoff_jitter: float = 0.2
    """+/- 20% jitter so many cameras reconnecting together don't do it in
    lockstep and hammer the source at the same instant."""
    max_consecutive_read_failures: int = 10
    """Trips the circuit breaker: a handful of dropped frames is normal
    (inter-frame gaps are explicitly not disconnects); a sustained run of
    failures means the connection is actually gone."""
    fallback_after_failures: int = 3
    """Consecutive failed opens on one URL before trying the next candidate
    (CaptureConfig.fallback_urls) — long enough not to abandon RTSP over one
    slow connect, short enough that a blocked port reaches HLS in seconds."""


@dataclass(slots=True)
class CameraSupervisor:
    """Async frame source for one camera. Reconnects itself; never raises out
    of `frames()` for a connection problem — only `stop()` ends the stream."""

    config: CaptureConfig
    supervisor_config: SupervisorConfig = field(default_factory=SupervisorConfig)
    capture_factory: Callable[[CaptureConfig], RtspCapture] = field(default=RtspCapture)
    # Called before each reconnect attempt, when there is anything the source
    # needs in place before it can be opened at all. For a camera consumed
    # through the local relay that is the relay path itself: it is registered
    # over MediaMTX's API rather than written into its config file, so a relay
    # restart silently drops every path and each camera then retries forever
    # against a path that no longer exists. Re-asserting it here means the
    # existing backoff loop repairs that, instead of needing the whole worker
    # restarted.
    on_reconnect: Callable[[], Awaitable[None]] | None = None
    # Decides, from a frame's timing alone, whether it is worth turning into
    # an image. Frames it declines are grabbed and timed but never converted
    # — see RtspCapture.grab. None decodes every frame. Loop cuts are always
    # decoded: the pipeline resets its tracker on them.
    decode_policy: Callable[[FrameTiming], bool] | None = None

    status: CameraStatus = field(default=CameraStatus.UNKNOWN, init=False)
    reconnects: int = field(default=0, init=False)
    _capture: RtspCapture = field(init=False)
    _stop_requested: bool = field(default=False, init=False)
    # Wakes a reconnect backoff early, so a stop does not wait out up to 36 s
    # of sleep on exactly the cameras most likely to be stopped (a wrong URL
    # or password leaves a camera at maximum backoff).
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _url_index: int = field(default=0, init=False)
    _open_failures_on_url: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._capture = self.capture_factory(self.config)

    @property
    def _urls(self) -> list[str]:
        return [self.config.url, *self.config.fallback_urls]

    @property
    def active_url(self) -> str:
        return self._urls[self._url_index]

    @property
    def on_fallback(self) -> bool:
        return self._url_index > 0

    def _note_open_failure(self) -> None:
        self._open_failures_on_url += 1
        if (
            len(self._urls) > 1
            and self._open_failures_on_url >= self.supervisor_config.fallback_after_failures
        ):
            self._url_index = (self._url_index + 1) % len(self._urls)
            self._open_failures_on_url = 0
            logger.warning(
                "%s: switching to %s after repeated failed opens",
                self.config.camera_id,
                "fallback stream" if self.on_fallback else "primary stream",
            )

    def _advance(self) -> Frame[np.ndarray] | _Skipped | None:
        """Runs in a worker thread: the next frame worth yielding, None on a
        read failure, or _SKIPPED when only skipped frames were read."""
        if self.decode_policy is None:
            return self._capture.read()
        for _ in range(_MAX_GRABS_PER_HOP):
            timing = self._capture.grab()
            if timing is None:
                return None
            if timing.is_discontinuity or self.decode_policy(timing):
                return self._capture.retrieve(timing)
        return _SKIPPED

    async def frames(self) -> AsyncIterator[Frame[np.ndarray]]:
        """Yield frames forever, reconnecting internally, until stop()."""
        backoff = self.supervisor_config.initial_backoff_s
        connected = False
        consecutive_failures = 0

        while not self._stop_requested:
            if not connected:
                self.status = CameraStatus.CONNECTING
                if self.reconnects and self.on_reconnect is not None:
                    await self.on_reconnect()
                opened = await asyncio.to_thread(self._capture.open, self.active_url)
                if not opened:
                    self._note_open_failure()
                    self.reconnects += 1
                    self.status = CameraStatus.DOWN
                    await self._sleep_with_jitter(backoff)
                    backoff = min(backoff * 2, self.supervisor_config.max_backoff_s)
                    continue

                self.status = CameraStatus.LIVE
                self._open_failures_on_url = 0
                backoff = self.supervisor_config.initial_backoff_s  # reset after success
                consecutive_failures = 0
                connected = True
                continue  # re-check stop_requested before the first read

            frame = await asyncio.to_thread(self._advance)
            if isinstance(frame, _Skipped):
                consecutive_failures = 0
                continue
            if frame is None:
                consecutive_failures += 1
                if consecutive_failures >= self.supervisor_config.max_consecutive_read_failures:
                    # Circuit breaker: this is a dead connection, not a
                    # transient gap (those are normal and handled inside the
                    # StreamClock, not here). Close and reconnect.
                    self.status = CameraStatus.DEGRADED
                    self._capture.close()
                    connected = False
                    self.reconnects += 1
                    # A connection that worked and then died says nothing
                    # about whether the primary is blocked; prefer it again.
                    self._url_index = 0
                    self._open_failures_on_url = 0
                continue

            consecutive_failures = 0
            yield frame

        self._capture.close()

    async def _sleep_with_jitter(self, backoff_s: float) -> None:
        jitter = backoff_s * random.uniform(
            -self.supervisor_config.backoff_jitter, self.supervisor_config.backoff_jitter
        )
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(0.0, backoff_s + jitter))

    def stop(self) -> None:
        self._stop_requested = True
        self._stop_event.set()

    @property
    def measured_fps(self) -> float | None:
        return self._capture.measured_fps

    @property
    def declared_fps(self) -> float | None:
        return self._capture.declared_fps

    @property
    def discontinuities(self) -> int:
        return self._capture.discontinuities
