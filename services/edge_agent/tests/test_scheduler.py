"""AnalysisScheduler: how much of each camera's stream reaches inference."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import numpy as np

from edge_agent.analytics.scheduler import AnalysisScheduler, SchedulerConfig
from sentinel_core.clock import Frame, FrameTiming
from sentinel_core.schemas import AnalyticsTier

EPOCH = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


def _timing(seq: int, pts_ms: float, *, discontinuity: bool = False) -> FrameTiming:
    return FrameTiming(
        camera_id="cam",
        pts_ms=pts_ms,
        seq=seq,
        stream_epoch=EPOCH,
        observed_at=EPOCH + timedelta(milliseconds=pts_ms),
        delta_ms=40.0 if seq else 0.0,
        is_gap=False,
        is_discontinuity=discontinuity,
    )


def _stream(fps: float, seconds: float) -> list[FrameTiming]:
    interval = 1000.0 / fps
    return [_timing(i, i * interval) for i in range(int(fps * seconds))]


def _frame(timing: FrameTiming, image: np.ndarray) -> Frame[np.ndarray]:
    return Frame(timing=timing, image=image, width=image.shape[1], height=image.shape[0])


def test_continuous_tier_honours_the_stride() -> None:
    scheduler = AnalysisScheduler(AnalyticsTier.A_CONTINUOUS, SchedulerConfig(stride=3))

    decoded = [t.seq for t in _stream(25, 1) if scheduler.should_decode(t)]

    assert decoded == list(range(0, 25, 3))


def test_sampled_tier_holds_its_rate_whatever_the_camera_streams() -> None:
    for camera_fps in (15, 25, 30, 60):
        scheduler = AnalysisScheduler(AnalyticsTier.B_SAMPLED, SchedulerConfig(sampled_fps=8))

        decoded = sum(scheduler.should_decode(t) for t in _stream(camera_fps, 10))

        assert 75 <= decoded <= 85, (camera_fps, decoded)


def test_a_slow_camera_is_never_throttled_below_its_own_rate() -> None:
    scheduler = AnalysisScheduler(AnalyticsTier.B_SAMPLED, SchedulerConfig(sampled_fps=8))

    decoded = sum(scheduler.should_decode(t) for t in _stream(5, 10))

    assert decoded == 50


def test_a_loop_cut_restarts_pacing_even_though_pts_went_backwards() -> None:
    scheduler = AnalysisScheduler(AnalyticsTier.B_SAMPLED, SchedulerConfig(sampled_fps=8))
    for timing in _stream(25, 2):
        scheduler.should_decode(timing)

    assert scheduler.should_decode(_timing(50, 0.0, discontinuity=True))


def test_motion_gated_tier_checks_cheaply_and_analyses_only_while_things_move() -> None:
    config = SchedulerConfig(sampled_fps=8, motion_check_fps=2, motion_hold_s=1.0)
    scheduler = AnalysisScheduler(AnalyticsTier.C_MOTION_GATED, config)
    still = np.full((90, 160, 3), 80, dtype=np.uint8)
    moving = still.copy()
    moving[20:70, 40:120] = 220

    def run(seconds: tuple[float, float], image: np.ndarray, start_seq: int) -> tuple[int, int]:
        decoded = analysed = 0
        for i, timing in enumerate(_stream(25, seconds[1])):
            if timing.pts_ms < seconds[0] * 1000:
                continue
            shifted = _timing(start_seq + i, timing.pts_ms)
            if scheduler.should_decode(shifted):
                decoded += 1
                analysed += scheduler.should_analyse(_frame(shifted, image))
        return decoded, analysed

    quiet_decoded, quiet_analysed = run((0, 4), still, 0)
    assert quiet_decoded <= 9  # ~2 checks a second
    assert quiet_analysed == 0

    scheduler.should_analyse(_frame(_timing(1000, 4000.0), moving))
    busy_decoded, busy_analysed = run((4.04, 4.9), moving, 1001)
    assert busy_decoded >= 6  # back up to the sampled rate during motion
    assert busy_analysed == busy_decoded


def test_non_motion_tiers_analyse_every_decoded_frame() -> None:
    scheduler = AnalysisScheduler(AnalyticsTier.B_SAMPLED)
    image = np.zeros((48, 64, 3), dtype=np.uint8)

    assert scheduler.should_analyse(_frame(_timing(0, 0.0), image))


def test_a_stream_gap_does_not_trigger_a_burst_of_catch_up_frames() -> None:
    scheduler = AnalysisScheduler(AnalyticsTier.B_SAMPLED, SchedulerConfig(sampled_fps=8))
    for timing in _stream(25, 1):
        scheduler.should_decode(timing)

    after_gap = [_timing(100 + i, 5000.0 + i * 40.0) for i in range(25)]
    decoded = [t.pts_ms for t in after_gap if scheduler.should_decode(t)]

    assert decoded[0] == 5000.0
    assert all(b - a >= 120.0 for a, b in pairwise(decoded))
