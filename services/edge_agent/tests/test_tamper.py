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


def test_a_normal_in_focus_frame_reports_ok() -> None:
    detector = TamperDetector(consecutive_frames_required=1)

    status = detector.update(_noisy_frame(base=128))

    assert status == "ok"


def test_a_near_black_frame_reports_covered() -> None:
    detector = TamperDetector(consecutive_frames_required=1)
    covered = np.zeros((200, 200, 3), dtype=np.uint8)

    assert detector.update(covered) == "covered"


def test_a_flat_low_contrast_frame_reports_blurred() -> None:
    """Not black (so it's not "covered"), but genuinely lacking
    high-frequency detail — a smudged/defocused lens."""
    detector = TamperDetector(consecutive_frames_required=1)
    flat = np.full((200, 200, 3), 100, dtype=np.uint8)

    assert detector.update(flat) == "blurred"


def test_status_does_not_flip_on_a_single_noisy_reading() -> None:
    """A momentary anomaly (one bad frame) must not flip the reported
    status — only `consecutive_frames_required` consistent readings do."""
    detector = TamperDetector(consecutive_frames_required=5)
    for _ in range(3):
        detector.update(_noisy_frame(base=128))

    # One single "covered"-looking frame in the middle of otherwise-normal
    # frames should not be enough to flip status.
    status = detector.update(np.zeros((200, 200, 3), dtype=np.uint8))

    assert status == "ok"


def test_status_flips_after_enough_consecutive_readings() -> None:
    detector = TamperDetector(consecutive_frames_required=3)
    for _ in range(2):
        detector.update(_noisy_frame(base=128))

    covered = np.zeros((200, 200, 3), dtype=np.uint8)
    detector.update(covered)
    detector.update(covered)
    status = detector.update(covered)

    assert status == "covered"


def test_a_sudden_large_scene_shift_reports_moved() -> None:
    """The reference is a slow exponential average of prior frames, so a
    sudden, large, sustained shift in scene content (not explained by a
    passing object) reads as camera movement."""
    detector = TamperDetector(consecutive_frames_required=1)
    # Establish a stable reference: many frames of the same noisy scene.
    for i in range(30):
        detector.update(_noisy_frame(base=60, seed=i))

    # A completely different scene — simulates the camera being physically
    # reoriented to point somewhere else entirely.
    status = detector.update(_noisy_frame(base=220, seed=999))

    assert status == "moved"


def test_a_passing_vehicle_does_not_trigger_moved() -> None:
    """A small, localised bright patch (a vehicle passing through part of
    the frame) must not read as a full camera-movement event — the mean
    frame-to-reference difference stays well under the moved threshold."""
    detector = TamperDetector(consecutive_frames_required=1)
    for i in range(30):
        detector.update(_noisy_frame(base=60, seed=i))

    frame = _noisy_frame(base=60, seed=31)
    frame[80:120, 80:120] = 255  # a small bright patch — "a vehicle"

    assert detector.update(frame) == "ok"
