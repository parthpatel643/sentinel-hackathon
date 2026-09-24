"""CameraSupervisor owns reconnect/backoff/circuit-breaking. Backoff timings
are set to near-zero so the suite stays fast; the *ratios and bounds* are what
matter and are asserted directly against SupervisorConfig."""

from __future__ import annotations

import asyncio

import numpy as np

from edge_agent.pipeline.capture import CaptureConfig, RtspCapture
from edge_agent.pipeline.supervisor import CameraSupervisor, SupervisorConfig
from sentinel_core.clock import Frame
from sentinel_core.schemas import CameraStatus

from .fakes import FakeFrame, FakeVideoSource, make_backend_factory

_FAST_BACKOFF = SupervisorConfig(
    initial_backoff_s=0.01, max_backoff_s=0.05, backoff_jitter=0.0, max_consecutive_read_failures=3
)


def _capture_factory(source: FakeVideoSource) -> type:
    factory = make_backend_factory(source)

    def build(config: CaptureConfig) -> RtspCapture:
        return RtspCapture(config=config, backend_factory=factory)

    return build  # type: ignore[return-value]


async def _collect(
    supervisor: CameraSupervisor, count: int, timeout_s: float = 2.0
) -> list[Frame[np.ndarray]]:
    frames: list[Frame[np.ndarray]] = []
    async with asyncio.timeout(timeout_s):
        async for frame in supervisor.frames():
            frames.append(frame)
            if len(frames) >= count:
                supervisor.stop()
    return frames


async def test_yields_frames_from_a_healthy_camera() -> None:
    source = FakeVideoSource(frames=[FakeFrame(pts_ms=i * 40.0) for i in range(1, 6)])
    supervisor = CameraSupervisor(
        config=CaptureConfig(camera_id="cam-1", url="rtsp://x"),
        supervisor_config=_FAST_BACKOFF,
        capture_factory=_capture_factory(source),
    )

    frames = await _collect(supervisor, count=5)

    assert len(frames) == 5
    assert supervisor.status == CameraStatus.LIVE
    assert supervisor.reconnects == 0


async def test_reconnects_after_open_failure_and_reports_down() -> None:
    """A camera that is simply unreachable must not raise — it must retry."""
    source = FakeVideoSource(should_fail_open=True)
    supervisor = CameraSupervisor(
        config=CaptureConfig(camera_id="cam-2", url="rtsp://x"),
        supervisor_config=_FAST_BACKOFF,
        capture_factory=_capture_factory(source),
    )

    async def run_briefly() -> None:
        async for _ in supervisor.frames():
            pass  # pragma: no cover - never reached; camera never opens

    task = asyncio.create_task(run_briefly())
    await asyncio.sleep(0.1)
    supervisor.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert supervisor.status == CameraStatus.DOWN
    assert supervisor.reconnects > 0


async def test_circuit_breaker_trips_after_sustained_read_failures() -> None:
    """A handful of dropped frames is normal; a sustained run means the
    connection is actually gone and must trigger a reconnect, not a crash."""
    source = FakeVideoSource(
        frames=[FakeFrame(pts_ms=40.0)] + [FakeFrame(pts_ms=0.0, ok=False)] * 5
    )
    supervisor = CameraSupervisor(
        config=CaptureConfig(camera_id="cam-3", url="rtsp://x"),
        supervisor_config=_FAST_BACKOFF,
        capture_factory=_capture_factory(source),
    )

    frames = []

    async def run() -> None:
        async for frame in supervisor.frames():
            frames.append(frame)

    task = asyncio.create_task(run())
    # The source runs out of frames after the breaker trips once (this fake
    # has no more script to replay), so we poll for the reconnect rather than
    # waiting on a frame that will never come again.
    for _ in range(50):
        if supervisor.reconnects >= 1:
            break
        await asyncio.sleep(0.02)
    supervisor.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert len(frames) >= 1
    assert supervisor.reconnects >= 1


async def test_stop_ends_the_stream_without_counting_as_a_reconnect() -> None:
    source = FakeVideoSource(frames=[FakeFrame(pts_ms=40.0) for _ in range(100)])
    supervisor = CameraSupervisor(
        config=CaptureConfig(camera_id="cam-4", url="rtsp://x"),
        supervisor_config=_FAST_BACKOFF,
        capture_factory=_capture_factory(source),
    )

    frames = await _collect(supervisor, count=3)

    assert len(frames) == 3
    assert supervisor.reconnects == 0


def test_backoff_bounds_match_the_organisers_own_numbers() -> None:
    """'Start at ~2s, cap at ~30s.' The production default, not the fast test
    config, must actually match what was promised in the HLD."""
    config = SupervisorConfig()
    assert config.initial_backoff_s == 2.0
    assert config.max_backoff_s == 30.0


async def test_the_source_is_reasserted_before_each_retry() -> None:
    """A camera consumed through the local relay depends on a relay path that
    exists only in MediaMTX's memory — it is registered over the API, not
    written to its config. Restarting the relay therefore drops every path at
    once, and without this hook each camera retries forever against a path
    that is gone, recoverable only by restarting the whole worker.

    Observed in practice: bringing the compose stack back up left one camera
    permanently `down` while its pipeline dutifully reconnected.
    """
    source = FakeVideoSource(should_fail_open=True)
    reasserts = 0

    async def _reassert() -> None:
        nonlocal reasserts
        reasserts += 1

    supervisor = CameraSupervisor(
        config=CaptureConfig(camera_id="cam-relay", url="rtsp://x"),
        supervisor_config=_FAST_BACKOFF,
        capture_factory=_capture_factory(source),
        on_reconnect=_reassert,
    )

    async def run_briefly() -> None:
        async for _ in supervisor.frames():
            pass  # pragma: no cover - never reached; camera never opens

    task = asyncio.create_task(run_briefly())
    await asyncio.sleep(0.1)
    supervisor.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert reasserts > 0, "every retry must re-assert what the source depends on"


async def test_the_first_connection_does_not_reassert() -> None:
    """Only *re*-connections need it. The caller has already resolved the
    source to get the URL it passed in, so doing it again immediately would be
    a redundant round-trip on every camera at startup."""
    source = FakeVideoSource(frames=[FakeFrame(pts_ms=i * 40.0) for i in range(1, 4)])
    called = False

    async def _reassert() -> None:
        nonlocal called
        called = True

    supervisor = CameraSupervisor(
        config=CaptureConfig(camera_id="cam-first", url="rtsp://x"),
        supervisor_config=_FAST_BACKOFF,
        capture_factory=_capture_factory(source),
        on_reconnect=_reassert,
    )

    received = 0
    async for _ in supervisor.frames():
        received += 1
        if received == 2:
            supervisor.stop()

    assert not called
