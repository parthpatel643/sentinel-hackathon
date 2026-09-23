"""Tests for the zone-rules engine — pure geometry/state-machine logic, no
model weights, no ONNX Runtime, no live camera. Zones use normalised [0, 1]
frame coordinates throughout."""

from __future__ import annotations

from edge_agent.analytics.zone_rules import Zone, ZoneEvent, ZoneRuleEngine

# A simple square zone covering the frame's right half.
RIGHT_HALF = ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0))


def test_intrusion_fires_once_on_entry_and_not_again_while_still_inside() -> None:
    zone = Zone(zone_id="z1", name="Restricted", rule_type="intrusion", polygon=RIGHT_HALF)
    engine = ZoneRuleEngine([zone])

    # Track starts outside, then enters.
    events_1 = engine.update({1: (0.2, 0.5)}, now_s=0.0)
    events_2 = engine.update({1: (0.7, 0.5)}, now_s=1.0)
    events_3 = engine.update({1: (0.75, 0.5)}, now_s=2.0)

    assert events_1 == []
    assert len(events_2) == 1
    assert events_2[0].rule_type == "intrusion"
    assert events_2[0].track_id == 1
    assert events_3 == []  # still inside — no repeat


def test_intrusion_fires_again_after_leaving_and_re_entering() -> None:
    zone = Zone(zone_id="z1", name="Restricted", rule_type="intrusion", polygon=RIGHT_HALF)
    engine = ZoneRuleEngine([zone])

    engine.update({1: (0.7, 0.5)}, now_s=0.0)  # enter (fires)
    engine.update({1: (0.2, 0.5)}, now_s=1.0)  # leave
    events = engine.update({1: (0.7, 0.5)}, now_s=2.0)  # re-enter

    assert len(events) == 1
    assert events[0].rule_type == "intrusion"


def test_loitering_fires_only_after_the_dwell_threshold() -> None:
    zone = Zone(
        zone_id="z1",
        name="Loading Bay",
        rule_type="loitering",
        polygon=RIGHT_HALF,
        dwell_threshold_s=10.0,
    )
    engine = ZoneRuleEngine([zone])

    events_at_5s = engine.update({1: (0.7, 0.5)}, now_s=0.0)
    events_at_5s += engine.update({1: (0.7, 0.5)}, now_s=5.0)
    events_at_15s = engine.update({1: (0.7, 0.5)}, now_s=15.0)

    assert events_at_5s == []
    assert len(events_at_15s) == 1
    assert events_at_15s[0].rule_type == "loitering"
    assert events_at_15s[0].dwell_time_s == 15.0


def test_loitering_does_not_fire_twice_for_the_same_dwell() -> None:
    zone = Zone(
        zone_id="z1",
        name="Loading Bay",
        rule_type="loitering",
        polygon=RIGHT_HALF,
        dwell_threshold_s=10.0,
    )
    engine = ZoneRuleEngine([zone])

    engine.update({1: (0.7, 0.5)}, now_s=0.0)
    events_1 = engine.update({1: (0.7, 0.5)}, now_s=15.0)
    events_2 = engine.update({1: (0.7, 0.5)}, now_s=20.0)

    assert len(events_1) == 1
    assert events_2 == []


def test_loitering_resets_after_leaving_the_zone() -> None:
    zone = Zone(
        zone_id="z1",
        name="Loading Bay",
        rule_type="loitering",
        polygon=RIGHT_HALF,
        dwell_threshold_s=10.0,
    )
    engine = ZoneRuleEngine([zone])

    engine.update({1: (0.7, 0.5)}, now_s=0.0)
    engine.update({1: (0.7, 0.5)}, now_s=15.0)  # fires
    engine.update({1: (0.2, 0.5)}, now_s=16.0)  # leaves — resets dwell clock
    engine.update({1: (0.7, 0.5)}, now_s=17.0)  # re-enters
    events = engine.update({1: (0.7, 0.5)}, now_s=20.0)  # only 3s dwell so far

    assert events == []


def test_stopped_vehicle_fires_when_a_track_stays_still_past_the_threshold() -> None:
    zone = Zone(
        zone_id="z1",
        name="Highway Shoulder",
        rule_type="stopped_vehicle",
        polygon=RIGHT_HALF,
        dwell_threshold_s=5.0,
        stopped_speed_threshold=0.01,
    )
    engine = ZoneRuleEngine([zone])

    # Same position every frame -> zero speed, well under the threshold.
    all_events = []
    for t in range(0, 8):
        all_events.extend(engine.update({1: (0.7, 0.5)}, now_s=float(t)))

    assert len(all_events) == 1
    assert all_events[0].rule_type == "stopped_vehicle"


def test_stopped_vehicle_does_not_fire_for_a_genuinely_moving_track() -> None:
    zone = Zone(
        zone_id="z1",
        name="Highway Shoulder",
        rule_type="stopped_vehicle",
        polygon=RIGHT_HALF,
        dwell_threshold_s=5.0,
        stopped_speed_threshold=0.01,
    )
    engine = ZoneRuleEngine([zone])

    events: list[ZoneEvent] = []
    for i, t in enumerate(range(0, 8)):
        events = engine.update({1: (0.55 + i * 0.05, 0.5)}, now_s=float(t))

    assert events == []


def test_wrong_way_fires_when_heading_deviates_past_tolerance() -> None:
    zone = Zone(
        zone_id="z1",
        name="One-Way Exit",
        rule_type="wrong_way",
        polygon=RIGHT_HALF,
        expected_direction_deg=0.0,
        direction_tolerance_deg=45.0,
    )
    engine = ZoneRuleEngine([zone])

    # Moving straight "backwards" (heading ~180°) relative to the expected
    # 0° direction — well outside a 45° tolerance.
    all_events = []
    for i, t in enumerate(range(0, 5)):
        all_events.extend(engine.update({1: (0.9 - i * 0.05, 0.5)}, now_s=float(t)))

    assert len(all_events) == 1
    assert all_events[0].rule_type == "wrong_way"
    assert all_events[0].heading_deg is not None


def test_wrong_way_does_not_fire_for_the_expected_direction() -> None:
    zone = Zone(
        zone_id="z1",
        name="One-Way Exit",
        rule_type="wrong_way",
        polygon=RIGHT_HALF,
        expected_direction_deg=0.0,
        direction_tolerance_deg=45.0,
    )
    engine = ZoneRuleEngine([zone])

    events: list[ZoneEvent] = []
    for i, t in enumerate(range(0, 5)):
        events = engine.update({1: (0.55 + i * 0.05, 0.5)}, now_s=float(t))

    assert events == []


def test_a_track_outside_every_zone_never_fires_anything() -> None:
    zone = Zone(zone_id="z1", name="Restricted", rule_type="intrusion", polygon=RIGHT_HALF)
    engine = ZoneRuleEngine([zone])

    events = engine.update({1: (0.1, 0.1)}, now_s=0.0)

    assert events == []


def test_two_tracks_are_evaluated_independently() -> None:
    zone = Zone(zone_id="z1", name="Restricted", rule_type="intrusion", polygon=RIGHT_HALF)
    engine = ZoneRuleEngine([zone])

    events = engine.update({1: (0.7, 0.5), 2: (0.1, 0.5)}, now_s=0.0)

    assert len(events) == 1
    assert events[0].track_id == 1


def test_a_track_that_disappears_is_forgotten_not_leaked() -> None:
    """A track that ages out of the tracker (vehicle left frame) must not
    keep contributing stale state forever."""
    zone = Zone(
        zone_id="z1",
        name="Loading Bay",
        rule_type="loitering",
        polygon=RIGHT_HALF,
        dwell_threshold_s=10.0,
    )
    engine = ZoneRuleEngine([zone])

    engine.update({1: (0.7, 0.5)}, now_s=0.0)
    engine.update({}, now_s=1.0)  # track 1 vanished
    # Track 1 reappears — if state leaked, this dwell would look like 20s
    # (started at t=0) instead of a fresh entry.
    engine.update({1: (0.7, 0.5)}, now_s=20.0)
    events = engine.update({1: (0.7, 0.5)}, now_s=21.0)

    assert events == []  # only ~1s of dwell since re-appearing, not 21s
