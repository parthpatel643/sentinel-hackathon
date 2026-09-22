"""SimpleTracker — Kalman-filtered IoU association.

Exercises the properties that make cross-camera route reconstruction possible
at all: a stable id across a smooth trajectory, a NEW id for a spatially
distinct vehicle, survival across a brief occlusion, and a hard reset on a
stream discontinuity (loop cut) so two unrelated vehicles never merge under
one id across a scene cut.
"""

from __future__ import annotations

from edge_agent.analytics.tracker import SimpleTracker, TrackerConfig
from edge_agent.analytics.vehicle_detector import VehicleDetection


def _car_at(x: float, y: float, size: float = 100.0, conf: float = 0.9) -> VehicleDetection:
    return VehicleDetection(
        bbox_xyxy=(x, y, x + size, y + size), vehicle_class="car", confidence=conf
    )


def test_a_single_smoothly_moving_vehicle_keeps_one_track_id() -> None:
    tracker = SimpleTracker()

    ids = []
    for step in range(10):
        tracked = tracker.update([_car_at(x=100.0 + step * 5, y=200.0)])
        ids.append(tracked[0].track_id)

    assert len(set(ids)) == 1


def test_two_spatially_distinct_vehicles_get_different_track_ids() -> None:
    tracker = SimpleTracker()

    tracked = tracker.update([_car_at(x=0.0, y=0.0), _car_at(x=800.0, y=800.0)])

    assert len({t.track_id for t in tracked}) == 2


def test_track_survives_a_brief_occlusion_with_the_same_id() -> None:
    """A vehicle that drops out for a couple of frames (occlusion, a missed
    detection) must re-associate with its existing track, not spawn a new
    one — this is what makes a track's plate-vote history meaningful."""
    tracker = SimpleTracker(TrackerConfig(max_age=5))

    first = tracker.update([_car_at(x=100.0, y=200.0)])
    original_id = first[0].track_id

    tracker.update([])  # occluded
    tracker.update([])  # still occluded

    reappeared = tracker.update([_car_at(x=110.0, y=200.0)])

    assert reappeared[0].track_id == original_id


def test_track_is_dropped_after_exceeding_max_age() -> None:
    """Beyond max_age, the vehicle is presumed gone; a later detection at the
    same spot must be treated as a new sighting, not a resurrection."""
    tracker = SimpleTracker(TrackerConfig(max_age=2))

    first = tracker.update([_car_at(x=100.0, y=200.0)])
    original_id = first[0].track_id

    tracker.update([])
    tracker.update([])
    tracker.update([])  # exceeds max_age=2

    reappeared = tracker.update([_car_at(x=100.0, y=200.0)])

    assert reappeared[0].track_id != original_id


def test_reset_clears_all_tracks_on_a_stream_discontinuity() -> None:
    """A loop cut / scene discontinuity must not let a track from the old
    scene silently merge with an unrelated vehicle in the new one."""
    tracker = SimpleTracker()
    before_id = tracker.update([_car_at(x=100.0, y=200.0)])[0].track_id

    tracker.reset()
    tracked = tracker.update([_car_at(x=100.0, y=200.0)])

    # The id counter does not need to restart, but this must be a genuinely
    # new track object, not the pre-reset one continuing under the same id.
    assert tracked[0].track_id != before_id
    assert tracked[0].hits == 1
    assert tracked[0].age == 0


def test_no_detections_returns_no_tracks() -> None:
    tracker = SimpleTracker()
    assert tracker.update([]) == []


def test_confirmed_track_reports_the_latest_detections_class_and_confidence() -> None:
    tracker = SimpleTracker()
    tracker.update([_car_at(x=100.0, y=200.0, conf=0.5)])

    tracked = tracker.update([_car_at(x=105.0, y=200.0, conf=0.95)])

    assert tracked[0].detection.confidence == 0.95
