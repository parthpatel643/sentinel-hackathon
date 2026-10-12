"""SimpleTracker — Kalman-filtered IoU association, timed by PTS.

Exercises the properties that make cross-camera route reconstruction possible
at all: a stable id across a smooth trajectory, a NEW id for a spatially
distinct vehicle, survival across a brief occlusion, and a hard reset on a
stream discontinuity (loop cut) so two unrelated vehicles never merge under
one id across a scene cut. And that time is the stream's PTS: unevenly spaced
frames, gaps and a reconnect's fast-delivered GOP must not change the motion
the tracker infers.
"""

from __future__ import annotations

from edge_agent.analytics.tracker import SimpleTracker, TrackerConfig
from edge_agent.analytics.vehicle_detector import VehicleDetection

FRAME_MS = 125.0  # the nominal 8 fps analysis rate


def _car_at(x: float, y: float, size: float = 100.0, conf: float = 0.9) -> VehicleDetection:
    return VehicleDetection(
        bbox_xyxy=(x, y, x + size, y + size), vehicle_class="car", confidence=conf
    )


def test_a_single_smoothly_moving_vehicle_keeps_one_track_id() -> None:
    tracker = SimpleTracker()

    ids = []
    for step in range(10):
        tracked = tracker.update([_car_at(x=100.0 + step * 5, y=200.0)], pts_ms=step * FRAME_MS)
        ids.append(tracked[0].track_id)

    assert len(set(ids)) == 1


def test_two_spatially_distinct_vehicles_get_different_track_ids() -> None:
    tracker = SimpleTracker()

    tracked = tracker.update([_car_at(x=0.0, y=0.0), _car_at(x=800.0, y=800.0)], pts_ms=0.0)

    assert len({t.track_id for t in tracked}) == 2


def test_track_survives_a_brief_occlusion_with_the_same_id() -> None:
    """A vehicle that drops out for a couple of frames (occlusion, a missed
    detection) must re-associate with its existing track, not spawn a new
    one — this is what makes a track's plate-vote history meaningful."""
    tracker = SimpleTracker(TrackerConfig(max_age_s=0.6))

    first = tracker.update([_car_at(x=100.0, y=200.0)], pts_ms=0.0)
    original_id = first[0].track_id

    tracker.update([], pts_ms=125.0)  # occluded
    tracker.update([], pts_ms=250.0)  # still occluded

    reappeared = tracker.update([_car_at(x=110.0, y=200.0)], pts_ms=375.0)

    assert reappeared[0].track_id == original_id


def test_track_is_dropped_after_exceeding_max_age() -> None:
    """Beyond max_age_s of footage, the vehicle is presumed gone; a later
    detection at the same spot must be treated as a new sighting, not a
    resurrection."""
    tracker = SimpleTracker(TrackerConfig(max_age_s=0.3))

    first = tracker.update([_car_at(x=100.0, y=200.0)], pts_ms=0.0)
    original_id = first[0].track_id

    tracker.update([], pts_ms=125.0)
    tracker.update([], pts_ms=250.0)
    tracker.update([], pts_ms=375.0)  # 375 ms unmatched: past max_age_s

    reappeared = tracker.update([_car_at(x=100.0, y=200.0)], pts_ms=500.0)

    assert reappeared[0].track_id != original_id


def test_reset_clears_all_tracks_on_a_stream_discontinuity() -> None:
    """A loop cut / scene discontinuity must not let a track from the old
    scene silently merge with an unrelated vehicle in the new one."""
    tracker = SimpleTracker()
    before_id = tracker.update([_car_at(x=100.0, y=200.0)], pts_ms=5000.0)[0].track_id

    tracker.reset()
    # After a cut the PTS origin moves; the new leg may start lower.
    tracked = tracker.update([_car_at(x=100.0, y=200.0)], pts_ms=0.0)

    # The id counter does not need to restart, but this must be a genuinely
    # new track object, not the pre-reset one continuing under the same id.
    assert tracked[0].track_id != before_id
    assert tracked[0].hits == 1
    assert tracked[0].age == 0


def test_no_detections_returns_no_tracks() -> None:
    tracker = SimpleTracker()
    assert tracker.update([], pts_ms=0.0) == []


def test_confirmed_track_reports_the_latest_detections_class_and_confidence() -> None:
    tracker = SimpleTracker()
    tracker.update([_car_at(x=100.0, y=200.0, conf=0.5)], pts_ms=0.0)

    tracked = tracker.update([_car_at(x=105.0, y=200.0, conf=0.95)], pts_ms=FRAME_MS)

    assert tracked[0].detection.confidence == 0.95


def _track_ids(tracker: SimpleTracker, frames: list[tuple[float, float]]) -> list[int]:
    """Feed one car at x=positions[i] at PTS pts[i]; return its track ids."""
    return [tracker.update([_car_at(x=x, y=200.0)], pts_ms=pts)[0].track_id for pts, x in frames]


def test_a_gap_in_the_footage_is_predicted_by_its_duration() -> None:
    """A car at 320 px/s (40 px per 125 ms frame), then half a second of
    footage the grid never delivered. Counting frames, the filter would
    predict 40 px of travel and miss the car 160 px further on; timed by
    PTS it predicts the 160 px and keeps the identity."""
    tracker = SimpleTracker()
    frames = [(i * FRAME_MS, 100.0 + 40.0 * i) for i in range(8)]
    last_pts, last_x = frames[-1]
    frames.append((last_pts + 500.0, last_x + 160.0))
    assert len(set(_track_ids(tracker, frames))) == 1


def test_fast_delivered_frames_do_not_inflate_velocity() -> None:
    """On connect the gateway replays its buffered GOP, so frames arrive
    faster than real time; their PTS still say 40 ms apart. A car at
    200 px/s moves 8 px per buffered frame and 25 px per normal one, and
    the estimated velocity carries across the switch without a jump."""
    tracker = SimpleTracker()
    burst = [(i * 40.0, 100.0 + 8.0 * i) for i in range(12)]
    ids = _track_ids(tracker, burst)
    after_burst = float(tracker._tracks[0].kf.statePost[4, 0])
    assert abs(after_burst - 200.0) < 20.0, f"{after_burst:.0f} px/s after the burst, not ~200"

    pts, x = burst[-1]
    steady = [(pts + k * FRAME_MS, x + 25.0 * k) for k in range(1, 8)]
    ids += _track_ids(tracker, steady)
    assert len(set(ids)) == 1
    velocity = float(tracker._tracks[0].kf.statePost[4, 0])
    assert abs(velocity - 200.0) < 20.0, f"velocity {velocity:.0f} px/s, expected ~200"


def test_track_lifetime_is_footage_time_whatever_the_frame_rate() -> None:
    """A vehicle hidden for two seconds outlives max_age_s=3 at 25 fps and at
    2 fps alike; counted in frames, the 25 fps camera would lose it first."""
    for fps in (25.0, 2.0):
        tracker = SimpleTracker(TrackerConfig(max_age_s=3.0))
        step = 1000.0 / fps
        original = tracker.update([_car_at(x=100.0, y=200.0)], pts_ms=0.0)[0].track_id
        hidden = int(2000.0 / step)
        for k in range(1, hidden + 1):
            tracker.update([], pts_ms=k * step)
        again = tracker.update([_car_at(x=100.0, y=200.0)], pts_ms=(hidden + 1) * step)
        assert again[0].track_id == original, f"lost after 2 s at {fps} fps"


def test_a_reordered_frame_advances_no_time() -> None:
    """A B-frame presented just before the newest frame seen must not run
    the filter backwards."""
    tracker = SimpleTracker()
    ids = _track_ids(tracker, [(0.0, 100.0), (125.0, 105.0), (100.0, 104.0), (250.0, 110.0)])
    assert len(set(ids)) == 1
