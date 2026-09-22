"""RTSP capture over OpenCV's FFmpeg backend.

Deliberately mirrors the organisers' own reference snippet (force TCP via
`OPENCV_FFMPEG_CAPTURE_OPTIONS`, read `CAP_PROP_POS_MSEC` for timing) rather
than inventing a bespoke decode path — matching their example is itself a
signal that we read the integrator guide carefully.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import cv2
import numpy as np

from sentinel_core.clock import Frame, StreamClock

__all__ = ["CaptureConfig", "RtspCapture", "VideoSource", "force_rtsp_tcp_transport"]

# UDP is accepted by RTSP servers but fails across NAT and most corporate
# firewalls; partial UDP delivery produces corrupt frames that look exactly
# like model bugs. This must be set before the first capture opens in the
# process, so it is applied both at import time and callable again explicitly.
_RTSP_TCP_OPTION = "rtsp_transport;tcp"


def force_rtsp_tcp_transport() -> None:
    """Force every OpenCV/FFmpeg RTSP capture in this process onto TCP, and
    quiet libav's own stderr logging.

    Join-time decoder warnings ("Could not find ref with POC", "co located
    POCs unavailable") are expected and self-correcting per the integrator
    guide, not evidence of a bug — but left at ffmpeg's default verbosity they
    drown out everything else, especially with many concurrent streams. This
    quiets libav directly (`OPENCV_FFMPEG_LOGLEVEL`); it does not touch our
    own structured logging, which is where a *sustained* failure is reported.
    """
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = _RTSP_TCP_OPTION
    os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")  # AV_LOG_QUIET


force_rtsp_tcp_transport()


class VideoSource(Protocol):
    """The slice of cv2.VideoCapture's interface we depend on.

    A Protocol rather than a subclass so tests can supply a synthetic source
    with a controlled PTS sequence, without needing a live RTSP server.
    """

    def isOpened(self) -> bool: ...  # noqa: N802 - matches cv2's naming
    def read(self) -> tuple[bool, np.ndarray | None]: ...
    def get(self, prop_id: int) -> float: ...
    def set(self, prop_id: int, value: float) -> bool: ...
    def release(self) -> None: ...


def _default_backend_factory(url: str) -> VideoSource:
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG)


@dataclass(slots=True)
class CaptureConfig:
    camera_id: str
    url: str
    hw_acceleration: bool = True
    """Best-effort request for CAP_PROP_HW_ACCELERATION=ANY (VideoToolbox on
    Apple Silicon, NVDEC/QuickSync elsewhere). Decode still proceeds in
    software if the backend cannot honour it — this is a hint, not a
    requirement, matching go2rtc's own finding that software sometimes wins."""


@dataclass(slots=True)
class CaptureStats:
    """Cheap, always-on counters. These back the ops dashboard's per-camera
    health tile and the M1 capacity benchmark."""

    frames_read: int = 0
    read_failures: int = 0
    gaps: int = 0
    discontinuities: int = 0


@dataclass(slots=True)
class RtspCapture:
    """One camera's capture session.

    Owns exactly one VideoSource and one StreamClock. The supervisor (see
    supervisor.py) owns reconnect/backoff; this class only knows how to be
    open, read a frame, or be closed.
    """

    config: CaptureConfig
    backend_factory: Callable[[str], VideoSource] = field(default=_default_backend_factory)
    stats: CaptureStats = field(default_factory=CaptureStats)
    _source: VideoSource | None = field(default=None, init=False)
    _clock: StreamClock = field(init=False)
    _declared_fps: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._clock = StreamClock(self.config.camera_id)

    def open(self) -> bool:
        source = self.backend_factory(self.config.url)
        if self.config.hw_acceleration:
            with contextlib.suppress(cv2.error):  # backend-dependent; best-effort only
                source.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY)
        if not source.isOpened():
            return False
        self._source = source
        # Metadata only — never used for timing. See declared_fps property.
        fps = source.get(cv2.CAP_PROP_FPS)
        self._declared_fps = fps if fps > 0 else None
        self._clock.reset()
        return True

    def read(self) -> Frame[np.ndarray] | None:
        """Read one frame, or None on a transient read failure.

        None does not necessarily mean the connection is dead — the caller
        (the supervisor) decides how many consecutive failures trip the
        circuit breaker, so a single dropped frame never tears down a
        healthy connection.
        """
        if self._source is None:
            raise RuntimeError(f"{self.config.camera_id}: read() before open()")

        ok, image = self._source.read()
        if not ok or image is None:
            self.stats.read_failures += 1
            return None

        pts_ms = self._source.get(cv2.CAP_PROP_POS_MSEC)
        timing = self._clock.observe(pts_ms)

        self.stats.frames_read += 1
        if timing.is_gap:
            self.stats.gaps += 1
        if timing.is_discontinuity:
            self.stats.discontinuities += 1

        height, width = image.shape[:2]
        return Frame(timing=timing, image=image, width=width, height=height)

    def close(self) -> None:
        if self._source is not None:
            self._source.release()
            self._source = None

    @property
    def is_open(self) -> bool:
        return self._source is not None

    @property
    def declared_fps(self) -> float | None:
        """CAP_PROP_FPS as reported by the container/demuxer. Metadata only —
        it routinely disagrees with the real delivery rate. See measured_fps."""
        return self._declared_fps

    @property
    def measured_fps(self) -> float | None:
        """The real rate, derived from PTS deltas over a rolling window."""
        return self._clock.measured_fps

    @property
    def discontinuities(self) -> int:
        return self._clock.discontinuities
