"""RtspCapture wraps a VideoSource and converts pos_msec into StreamClock
timing. The fake source lets us script failures without a live RTSP server."""

from __future__ import annotations

from edge_agent.pipeline.capture import CaptureConfig, RtspCapture

from .fakes import FakeFrame, FakeVideoSource, make_backend_factory


def _capture(source: FakeVideoSource, camera_id: str = "cam-test") -> RtspCapture:
    return RtspCapture(
        config=CaptureConfig(camera_id=camera_id, url="rtsp://example/test"),
        backend_factory=make_backend_factory(source),
    )


def test_open_fails_cleanly_when_the_camera_is_unreachable() -> None:
    source = FakeVideoSource(should_fail_open=True)
    capture = _capture(source)

    assert capture.open() is False
    assert not capture.is_open


def test_open_succeeds_and_captures_declared_fps_as_metadata() -> None:
    source = FakeVideoSource(declared_fps=24.97)
    capture = _capture(source)

    assert capture.open() is True
    assert capture.declared_fps == 24.97


def test_read_converts_pos_msec_into_frame_timing() -> None:
    source = FakeVideoSource(frames=[FakeFrame(pts_ms=40.0), FakeFrame(pts_ms=80.0)])
    capture = _capture(source)
    capture.open()

    first = capture.read()
    second = capture.read()

    assert first is not None
    assert second is not None
    assert first.timing.pts_ms == 40.0
    assert second.timing.pts_ms == 80.0
    assert second.timing.delta_ms == 40.0


def test_read_returns_none_on_a_transient_failure_without_raising() -> None:
    """A single dropped frame is not a disconnect — the supervisor decides how
    many failures in a row actually mean something is wrong."""
    source = FakeVideoSource(frames=[FakeFrame(pts_ms=40.0, ok=False)])
    capture = _capture(source)
    capture.open()

    assert capture.read() is None
    assert capture.stats.read_failures == 1


def test_read_before_open_raises_instead_of_silently_returning_none() -> None:
    import pytest

    capture = _capture(FakeVideoSource())
    with pytest.raises(RuntimeError, match="before open"):
        capture.read()


def test_measured_fps_tracks_pts_not_declared_fps() -> None:
    """The whole point: measured_fps must reflect the *real* delivery rate."""
    source = FakeVideoSource(
        declared_fps=30.0,  # deliberately wrong
        frames=[FakeFrame(pts_ms=i * 100.0) for i in range(1, 10)],  # actually 10 fps
    )
    capture = _capture(source)
    capture.open()
    for _ in range(9):
        capture.read()

    assert capture.declared_fps == 30.0
    assert capture.measured_fps is not None
    assert abs(capture.measured_fps - 10.0) < 0.01


def test_close_releases_the_underlying_source() -> None:
    source = FakeVideoSource()
    capture = _capture(source)
    capture.open()

    capture.close()

    assert source.released
    assert not capture.is_open


def test_reopening_resets_the_clock_so_a_reconnect_does_not_look_like_a_cut() -> None:
    """A fresh connection legitimately restarts its own PTS numbering. That
    must not be reported as a mid-stream scene discontinuity."""
    source = FakeVideoSource(frames=[FakeFrame(pts_ms=40.0), FakeFrame(pts_ms=80.0)])
    capture = _capture(source)
    capture.open()
    capture.read()
    capture.read()
    capture.close()

    source.frames = [FakeFrame(pts_ms=0.0), FakeFrame(pts_ms=40.0)]
    source.rewind()
    capture.open()
    first = capture.read()

    assert first is not None
    assert not first.timing.is_discontinuity
