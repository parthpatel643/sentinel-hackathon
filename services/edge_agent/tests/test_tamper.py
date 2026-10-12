"""Tests for the frame-statistics camera tamper detector — pure pixel
math, no model weights, no ONNX Runtime."""

from __future__ import annotations

import numpy as np

from edge_agent.analytics.tamper import TamperDetector


def _noisy_frame(base: int, size: int = 200, seed: int = 0) -> np.ndarray:
    """A frame with genuine local contrast (unlike a flat colour), so
    Laplacian variance is high — a stand-in for a normal, in-focus scene."""
    rng = np.random.default_rng(seed)
    noise = rng.integers(-20, 20, size=(size, size, 3))
    frame = np.clip(base + noise, 0, 255).astype(np.uint8)
    return frame


COVERED = np.zeros((200, 200, 3), dtype=np.uint8)


def _first_flip_ms(detector: TamperDetector, pts: list[float]) -> float | None:
    """Feed a covered lens at these PTS; the PTS at which status flips."""
    for pts_ms in pts:
        if detector.update(COVERED, pts_ms=pts_ms) == "covered":
            return pts_ms
    return None


def test_a_normal_in_focus_frame_reports_ok() -> None:
    detector = TamperDetector(sustained_s=0.0, min_readings=1)

    status = detector.update(_noisy_frame(base=128), pts_ms=0.0)

    assert status == "ok"


def test_a_near_black_frame_reports_covered() -> None:
    detector = TamperDetector(sustained_s=0.0, min_readings=1)
    covered = np.zeros((200, 200, 3), dtype=np.uint8)

    assert detector.update(covered, pts_ms=0.0) == "covered"


def test_a_flat_low_contrast_frame_reports_blurred() -> None:
    """Not black (so it's not "covered"), but genuinely lacking
    high-frequency detail — a smudged/defocused lens."""
    detector = TamperDetector(sustained_s=0.0, min_readings=1)
    flat = np.full((200, 200, 3), 100, dtype=np.uint8)

    assert detector.update(flat, pts_ms=0.0) == "blurred"


def test_status_does_not_flip_on_a_single_noisy_reading() -> None:
    """A momentary anomaly (one bad frame) must not flip the reported
    status — only a reading sustained over footage does."""
    detector = TamperDetector()
    for i in range(3):
        detector.update(_noisy_frame(base=128), pts_ms=i * 125.0)

    # One single "covered"-looking frame in the middle of otherwise-normal
    # frames should not be enough to flip status.
    status = detector.update(COVERED, pts_ms=375.0)

    assert status == "ok"


def test_status_flips_after_half_a_second_of_footage_at_8_fps() -> None:
    """The analysis rate is 8 fps: five frames, as the old frame count was."""
    detector = TamperDetector()
    for i in range(2):
        detector.update(_noisy_frame(base=128), pts_ms=i * 125.0)

    assert _first_flip_ms(detector, [250.0 + i * 125.0 for i in range(8)]) == 750.0


def test_a_fast_burst_of_frames_does_not_flip_status_early() -> None:
    """On connect the gateway replays its buffered GOP faster than real time:
    a dozen frames 10 ms apart in PTS are a tenth of a second of footage, not
    twelve frames' worth."""
    detector = TamperDetector()
    assert _first_flip_ms(detector, [i * 10.0 for i in range(12)]) is None
    assert detector.current_status == "ok"


def test_the_same_footage_flips_at_the_same_time_however_it_was_sampled() -> None:
    def flip_at(step_ms: float) -> float | None:
        return _first_flip_ms(TamperDetector(), [i * step_ms for i in range(40)])

    for step_ms in (20.0, 50.0, 125.0, 250.0):
        assert flip_at(step_ms) == 500.0, step_ms


def test_one_frame_either_side_of_a_gap_is_not_enough() -> None:
    """Two frames can span half a second with nothing watched between them;
    the minimum number of frames stops that, and a gap adds no more footage
    than the slowest decode interval (0.25 s)."""
    assert _first_flip_ms(TamperDetector(), [0.0, 600.0]) is None
    assert _first_flip_ms(TamperDetector(), [0.0, 5_000.0, 5_125.0, 5_250.0]) == 5_250.0


def test_a_repeated_pts_is_not_another_reading() -> None:
    detector = TamperDetector()
    assert _first_flip_ms(detector, [0.0, 0.0, 0.0, 250.0, 250.0, 250.0]) is None
    assert _first_flip_ms(detector, [500.0]) == 500.0


def test_pts_going_back_restarts_the_run_but_keeps_the_status() -> None:
    """A reconnect restarts PTS: footage on the old timeline is not added to
    the new one, and a status already confirmed stays as it was."""
    detector = TamperDetector()
    assert _first_flip_ms(detector, [60_000.0 + i * 125.0 for i in range(4)]) is None
    # PTS restarts at 0: had the old run carried on, this frame would flip it.
    assert detector.update(COVERED, pts_ms=0.0) == "ok"
    assert _first_flip_ms(detector, [125.0, 250.0, 375.0, 500.0]) == 500.0

    for i in range(1, 4):
        detector.update(_noisy_frame(base=128), pts_ms=500.0 + i * 125.0)
    detector.reset_timing()
    assert detector.update(_noisy_frame(base=128), pts_ms=1_000.0) == "covered"


def test_a_changed_scene_is_left_to_the_view_monitor() -> None:
    """A re-aimed camera is ViewMonitor's to report, geometrically. This
    detector judges only the frame itself: dark or out of focus."""
    detector = TamperDetector(sustained_s=0.0, min_readings=1)
    for i in range(30):
        detector.update(_noisy_frame(base=60, seed=i), pts_ms=i * 125.0)
    assert detector.update(_noisy_frame(base=220, seed=999), pts_ms=30 * 125.0) == "ok"
