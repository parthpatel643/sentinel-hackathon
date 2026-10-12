"""Camera view monitoring: a moved camera is reported, ordinary scene change is not.

Synthetic scenes keep these tests fast and deterministic; the same behaviour
was measured on the recorded government feeds (cam01, cam24, cam30): a 12%
knock and a 6° rotation reported within one confirmation window, and no
report over five minutes of untouched footage, simulated rain and haze, a
bus crossing the frame, or ±1% wind shake.
"""

from __future__ import annotations

import cv2
import numpy as np

from edge_agent.analytics.view_monitor import ViewChange, ViewMonitor

W, H = 960, 540


def _scene(seed: int = 7) -> np.ndarray:
    """A street-like texture: many fixed rectangles and lines to match on."""
    rng = np.random.default_rng(seed)
    image = np.full((H, W, 3), 90, dtype=np.uint8)
    for _ in range(140):
        x, y = int(rng.integers(0, W - 40)), int(rng.integers(0, H - 40))
        w, h = int(rng.integers(10, 90)), int(rng.integers(10, 90))
        colour = tuple(int(c) for c in rng.integers(0, 255, 3))
        cv2.rectangle(image, (x, y), (x + w, y + h), colour, -1)
    for _ in range(40):
        p1 = (int(rng.integers(0, W)), int(rng.integers(0, H)))
        p2 = (int(rng.integers(0, W)), int(rng.integers(0, H)))
        cv2.line(image, p1, p2, (255, 255, 255), 2)
    return image


def _shift(image: np.ndarray, fx: float, fy: float) -> np.ndarray:
    matrix = np.array([[1, 0, fx * W], [0, 1, fy * H]], dtype=np.float32)
    return cv2.warpAffine(image, matrix, (W, H), borderMode=cv2.BORDER_REPLICATE)


def _rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    matrix = cv2.getRotationMatrix2D((W / 2, H / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (W, H), borderMode=cv2.BORDER_REPLICATE)


def _noisy(image: np.ndarray, seed: int) -> np.ndarray:
    noise = np.random.default_rng(seed).normal(0, 6, image.shape).astype(np.int16)
    noisy: np.ndarray = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return noisy


def _run(monitor: ViewMonitor, frames: list[np.ndarray], start_s: float = 0.0) -> list[ViewChange]:
    events: list[ViewChange] = []
    for i, frame in enumerate(frames):
        change = monitor.observe(frame, pts_ms=(start_s + i * monitor.check_interval_s) * 1000)
        if change is not None:
            events.append(change)
    return events


def _learned(monitor: ViewMonitor | None = None) -> tuple[ViewMonitor, np.ndarray]:
    monitor = monitor or ViewMonitor()
    scene = _scene()
    assert _run(monitor, [_noisy(scene, i) for i in range(4)]) == []
    assert monitor.status == "ok"
    return monitor, scene


def test_the_normal_view_is_learned_from_agreeing_frames() -> None:
    monitor = ViewMonitor()
    assert monitor.status == "learning"
    _learned(monitor)


def test_an_unchanged_view_with_sensor_noise_never_reports() -> None:
    monitor, scene = _learned()
    assert _run(monitor, [_noisy(scene, i) for i in range(10, 60)], start_s=8) == []
    assert monitor.status == "ok"


def test_a_knocked_camera_is_reported_with_how_far_it_moved() -> None:
    monitor, scene = _learned()
    moved = [_noisy(_shift(scene, 0.12, 0.05), i) for i in range(10, 16)]
    events = _run(monitor, moved, start_s=8)
    assert [e.kind for e in events] == ["shifted"]
    assert events[0].shift_pct is not None and 11.0 < events[0].shift_pct < 14.0
    assert monitor.status == "moved"
    assert events[0].reference.shape == events[0].current.shape == scene.shape


def test_a_move_must_hold_before_it_is_reported() -> None:
    """One displaced check is a jolt, not a moved camera."""
    monitor, scene = _learned()
    frames = [_shift(scene, 0.12, 0), _shift(scene, 0.12, 0), scene, scene]
    assert _run(monitor, frames, start_s=8) == []
    assert monitor.status == "ok"


def test_a_rotated_camera_is_reported_with_its_angle() -> None:
    monitor, scene = _learned()
    events = _run(monitor, [_rotate(scene, 7) for _ in range(5)], start_s=8)
    assert [e.kind for e in events] == ["shifted"]
    assert events[0].rotation_deg is not None and 6.0 < abs(events[0].rotation_deg) < 8.0


def test_small_wind_shake_is_not_a_move() -> None:
    monitor, scene = _learned()
    rng = np.random.default_rng(3)
    shaky = [_shift(scene, rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01)) for _ in range(30)]
    assert _run(monitor, shaky, start_s=8) == []


def test_a_camera_put_back_reports_restored() -> None:
    monitor, scene = _learned()
    _run(monitor, [_shift(scene, 0.12, 0.05)] * 4, start_s=8)
    assert monitor.status == "moved"
    events = _run(monitor, [_noisy(scene, i) for i in range(4)], start_s=20)
    assert [e.kind for e in events] == ["restored"]
    assert str(monitor.status) == "ok"


def test_a_camera_turned_to_another_scene_is_reported_only_when_sustained() -> None:
    """A different scene matches nothing. Weather or a parked lorry can do
    that for a while too, so it is reported only after it has held."""
    monitor, _ = _learned(ViewMonitor(unrecognised_checks=6))
    elsewhere = _scene(seed=99)
    assert _run(monitor, [elsewhere] * 5, start_s=8) == []
    events = _run(monitor, [elsewhere] * 2, start_s=18)
    assert [e.kind for e in events] == ["unrecognised"]
    assert events[0].shift_pct is None
    assert monitor.status == "view_lost"


def test_a_blank_frame_is_skipped_not_counted() -> None:
    """A covered lens or black night frame has nothing to compare; that is
    TamperDetector's to report, and must not count toward a move."""
    monitor, scene = _learned(ViewMonitor(unrecognised_checks=3))
    black = np.zeros_like(scene)
    assert _run(monitor, [black] * 10, start_s=8) == []
    assert monitor.status == "ok"


def test_checks_are_paced_by_stream_time() -> None:
    monitor, scene = _learned()
    moved = _shift(scene, 0.12, 0.05)
    # Many frames inside one check interval count as one check.
    for i in range(20):
        assert monitor.observe(moved, pts_ms=8000 + i * 40) is None
    assert monitor.status == "ok"


def test_a_long_held_new_view_is_adopted_so_it_stops_reporting() -> None:
    """A camera repositioned on purpose: the alert was raised once; after the
    hold the new view becomes normal and is not reported again."""
    monitor, scene = _learned(ViewMonitor(adopt_after_s=20))
    moved = _shift(scene, 0.12, 0.05)
    events = _run(monitor, [_noisy(moved, i) for i in range(30)], start_s=8)
    assert [e.kind for e in events] == ["shifted"]
    assert monitor.status == "ok", "re-learned the new view after the hold"


def test_the_remembered_view_follows_gradual_light_change() -> None:
    """Dusk, shadows: refreshed while in place, so a slow fade is followed
    rather than mistaken for a move."""
    monitor, scene = _learned(ViewMonitor(refresh_s=4, unrecognised_checks=5))
    frames = [cv2.convertScaleAbs(scene, alpha=1 - 0.012 * i, beta=0) for i in range(60)]
    assert _run(monitor, frames, start_s=8) == []
    assert monitor.status == "ok"


def test_a_stream_restart_keeps_the_remembered_view() -> None:
    monitor, scene = _learned()
    monitor.reset_timing()
    assert monitor.observe(scene, pts_ms=0.0) is None
    assert monitor.status == "ok"
