"""Per-camera reconnect supervisor.

Owns exactly one camera's lifecycle: open, read until something goes wrong,
reconnect with exponential backoff. This is where the organisers' resilience
rules actually live — a capture that opens once and dies on the first hiccup
would fail the very first evaluation run.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

import numpy as np

from edge_agent.pipeline.capture import CaptureConfig, RtspCapture
from sentinel_core.clock import Frame
from sentinel_core.schemas import CameraStatus

__all__ = ["CameraSupervisor", "SupervisorConfig"]


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

    status: CameraStatus = field(default=CameraStatus.UNKNOWN, init=False)
    reconnects: int = field(default=0, init=False)
    _capture: RtspCapture = field(init=False)
    _stop_requested: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._capture = self.capture_factory(self.config)

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
                opened = await asyncio.to_thread(self._capture.open)
                if not opened:
                    self.reconnects += 1
                    self.status = CameraStatus.DOWN
                    await self._sleep_with_jitter(backoff)
                    backoff = min(backoff * 2, self.supervisor_config.max_backoff_s)
                    continue

                self.status = CameraStatus.LIVE
                backoff = self.supervisor_config.initial_backoff_s  # reset after success
                consecutive_failures = 0
                connected = True
                continue  # re-check stop_requested before the first read

            frame = await asyncio.to_thread(self._capture.read)
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
                continue

            consecutive_failures = 0
            yield frame

        self._capture.close()

    async def _sleep_with_jitter(self, backoff_s: float) -> None:
        jitter = backoff_s * random.uniform(
            -self.supervisor_config.backoff_jitter, self.supervisor_config.backoff_jitter
        )
        await asyncio.sleep(max(0.0, backoff_s + jitter))

    def stop(self) -> None:
        self._stop_requested = True

    @property
    def measured_fps(self) -> float | None:
        return self._capture.measured_fps

    @property
    def declared_fps(self) -> float | None:
        return self._capture.declared_fps

    @property
    def discontinuities(self) -> int:
        return self._capture.discontinuities
