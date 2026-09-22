"""The PTS clock is load-bearing: if it is wrong, every timestamp, track and
route in the platform is wrong. ADR-005."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sentinel_core.clock import StreamClock

ANCHOR = datetime(2026, 9, 22, 9, 0, 0, tzinfo=UTC)


def test_first_frame_anchors_to_wall_clock() -> None:
    clock = StreamClock("cam-1")
    timing = clock.observe(0.0, now=ANCHOR)

    assert timing.observed_at == ANCHOR
    assert timing.seq == 0
    assert timing.delta_ms == 0.0
    assert not timing.is_discontinuity


def test_observed_time_follows_pts_not_arrival() -> None:
    """The gateway replays a buffered GOP on connect, so several frames arrive
    within milliseconds of each other. Their timestamps must still be spaced by
    their PTS, or every tracker computes impossible velocities."""
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)

    burst = [clock.observe(pts) for pts in (200.0, 400.0, 600.0)]

    assert [t.observed_at for t in burst] == [
        ANCHOR + timedelta(milliseconds=200),
        ANCHOR + timedelta(milliseconds=400),
        ANCHOR + timedelta(milliseconds=600),
    ]
    assert [t.delta_ms for t in burst] == [200.0, 200.0, 200.0]


def test_measured_fps_is_derived_from_pts() -> None:
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)
    for i in range(1, 25):
        clock.observe(i * 40.0)  # 25 fps

    fps = clock.measured_fps
    assert fps is not None
    assert abs(fps - 25.0) < 0.01


def test_measured_fps_is_none_until_enough_frames() -> None:
    clock = StreamClock("cam-1")
    assert clock.measured_fps is None
    clock.observe(0.0, now=ANCHOR)
    assert clock.measured_fps is None


def test_small_backwards_jump_is_decoder_reordering_not_a_cut() -> None:
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)
    clock.observe(400.0)

    timing = clock.observe(360.0)

    assert not timing.is_discontinuity
    assert clock.discontinuities == 0


def _play(clock: StreamClock, *, duration_ms: float, step_ms: float = 40.0) -> None:
    """Advance a stream at a realistic frame cadence."""
    pts = step_ms
    while pts <= duration_ms:
        clock.observe(pts)
        pts += step_ms


def test_loop_cut_is_detected_when_pts_restarts() -> None:
    """The recorded feeds loop; at the loop point PTS restarts and the scene cuts
    like a camera reboot. Long-lived state must be told to reset."""
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)
    _play(clock, duration_ms=10_000.0)

    timing = clock.observe(0.0)

    assert timing.is_discontinuity
    assert clock.discontinuities == 1


def test_timeline_never_rewinds_across_a_loop_cut() -> None:
    """Evidence timestamps must stay monotonic even though PTS restarted."""
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)
    _play(clock, duration_ms=10_000.0 - 40.0)
    before = clock.observe(10_000.0)

    after = clock.observe(0.0)
    later = clock.observe(40.0)

    assert after.observed_at >= before.observed_at
    assert later.observed_at > after.observed_at


def test_stale_state_after_a_long_forward_jump_is_a_discontinuity() -> None:
    """A minute of PTS in one step means any tracker state is stale — treat it
    like a cut rather than feeding an absurd delta into a motion model."""
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)

    timing = clock.observe(60_000.0)

    assert timing.is_discontinuity
    assert clock.discontinuities == 1


def test_b_frame_reordering_is_not_mistaken_for_a_loop_cut() -> None:
    """With B-frames the previous frame can itself be out of presentation order,
    so discontinuity is judged against the highest PTS seen, not the last one."""
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)
    _play(clock, duration_ms=5_000.0)

    clock.observe(5_040.0)
    timing = clock.observe(4_960.0)  # reordered frame arrives after a later one

    assert not timing.is_discontinuity
    assert clock.discontinuities == 0


def test_gap_is_flagged_but_is_not_a_disconnect() -> None:
    """Inter-frame gaps are normal. They must widen motion-model uncertainty
    without tearing down the connection."""
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)

    timing = clock.observe(2_000.0)

    assert timing.is_gap
    assert not timing.is_discontinuity
    assert timing.delta_s == 2.0


def test_reset_forces_reanchor_on_reconnect() -> None:
    clock = StreamClock("cam-1")
    clock.observe(0.0, now=ANCHOR)
    clock.observe(1_000.0)

    clock.reset()
    later = ANCHOR + timedelta(seconds=30)
    timing = clock.observe(0.0, now=later)

    assert timing.observed_at == later
    assert timing.delta_ms == 0.0
