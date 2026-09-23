"""Zone rules — M13 secondary analytics: docs/05-DELIVERY-PLAN.md's "zone
rules (intrusion, loitering, wrong-way, stopped vehicle)." Built directly
on the existing per-camera `SimpleTracker`'s track history — no new model,
no new dependency (point-in-polygon is a small, well-understood ray-cast,
not worth pulling in a geometry library for at this scale).

Zone polygons are normalised (0.0-1.0) frame coordinates, not pixels — a
zone defined once for a camera stays correct even if that camera's stream
resolution changes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

__all__ = ["Zone", "ZoneEvent", "ZoneRuleEngine"]

RuleType = Literal["intrusion", "loitering", "wrong_way", "stopped_vehicle"]


@dataclass(frozen=True, slots=True)
class Zone:
    """One configured rule for one camera. `polygon` is a list of (x, y)
    points in normalised [0, 1] frame coordinates, at least 3 points.
    Rule-specific parameters are plain fields rather than a nested
    per-rule-type object — simpler to serialise, and only two rule types
    (`wrong_way`, the rest) actually need extra parameters at all."""

    zone_id: str
    name: str
    rule_type: RuleType
    polygon: tuple[tuple[float, float], ...]
    # loitering / stopped_vehicle: how long a track must dwell/stay still
    # before it counts as a violation, not just briefly passing through.
    dwell_threshold_s: float = 10.0
    # wrong_way: the expected direction of travel, degrees, 0 = frame's +x
    # axis, increasing clockwise (image coordinates) — and how far off
    # that a track's own bearing may be before it's flagged.
    expected_direction_deg: float = 0.0
    direction_tolerance_deg: float = 60.0
    # stopped_vehicle: below this speed (normalised frame-widths per
    # second), a track counts as "stopped," not just moving slowly.
    stopped_speed_threshold: float = 0.01


@dataclass(frozen=True, slots=True)
class ZoneEvent:
    zone_id: str
    zone_name: str
    rule_type: RuleType
    track_id: int
    dwell_time_s: float | None = None
    heading_deg: float | None = None


def _point_in_polygon(point: tuple[float, float], polygon: tuple[tuple[float, float], ...]) -> bool:
    """Standard ray-casting point-in-polygon test — O(n) in the polygon's
    vertex count, plenty fast for the handful of zones one camera has."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_intersect:
                inside = not inside
    return inside


@dataclass
class _TrackState:
    positions: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y, t_s)
    zone_entered_at: dict[str, float] = field(default_factory=dict)
    fired_rules: set[tuple[str, str]] = field(default_factory=set)  # (zone_id, rule_type)

    def record(self, x: float, y: float, t_s: float, *, history_s: float = 5.0) -> None:
        self.positions.append((x, y, t_s))
        cutoff = t_s - history_s
        while len(self.positions) > 1 and self.positions[0][2] < cutoff:
            self.positions.pop(0)

    def speed(self) -> float | None:
        """Normalised frame-widths per second, over the retained history."""
        if len(self.positions) < 2:
            return None
        x0, y0, t0 = self.positions[0]
        x1, y1, t1 = self.positions[-1]
        dt = t1 - t0
        if dt <= 0:
            return None
        return math.hypot(x1 - x0, y1 - y0) / dt

    def heading_deg(self) -> float | None:
        if len(self.positions) < 2:
            return None
        x0, y0, _ = self.positions[0]
        x1, y1, _ = self.positions[-1]
        if math.hypot(x1 - x0, y1 - y0) < 1e-6:
            return None  # not moving enough to have a meaningful heading
        return math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360


class ZoneRuleEngine:
    """One instance per camera. Feed it each frame's tracked-vehicle centre
    points (normalised 0-1 coordinates) in PTS order; `update()` returns
    any zone violations newly triggered this frame — de-duplicated per
    (track, zone, rule) so a vehicle sitting in a loitering zone for two
    minutes produces one event, not one every frame."""

    def __init__(self, zones: list[Zone]):
        self._zones = zones
        self._tracks: dict[int, _TrackState] = {}

    def update(self, positions: dict[int, tuple[float, float]], now_s: float) -> list[ZoneEvent]:
        events: list[ZoneEvent] = []
        active_ids = set(positions)
        for stale_id in set(self._tracks) - active_ids:
            del self._tracks[stale_id]

        for track_id, (x, y) in positions.items():
            state = self._tracks.setdefault(track_id, _TrackState())
            state.record(x, y, now_s)

            for zone in self._zones:
                inside = _point_in_polygon((x, y), zone.polygon)
                was_inside = zone.zone_id in state.zone_entered_at

                if zone.rule_type == "intrusion":
                    if inside and not was_inside:
                        state.zone_entered_at[zone.zone_id] = now_s
                        events.append(
                            ZoneEvent(
                                zone_id=zone.zone_id,
                                zone_name=zone.name,
                                rule_type="intrusion",
                                track_id=track_id,
                            )
                        )
                    elif not inside and was_inside:
                        del state.zone_entered_at[zone.zone_id]
                        state.fired_rules.discard((zone.zone_id, "intrusion"))
                    continue

                if zone.rule_type == "loitering":
                    if inside and not was_inside:
                        state.zone_entered_at[zone.zone_id] = now_s
                    elif not inside and was_inside:
                        del state.zone_entered_at[zone.zone_id]
                        state.fired_rules.discard((zone.zone_id, "loitering"))
                    if inside and zone.zone_id in state.zone_entered_at:
                        dwell = now_s - state.zone_entered_at[zone.zone_id]
                        key = (zone.zone_id, "loitering")
                        if dwell >= zone.dwell_threshold_s and key not in state.fired_rules:
                            state.fired_rules.add(key)
                            events.append(
                                ZoneEvent(
                                    zone_id=zone.zone_id,
                                    zone_name=zone.name,
                                    rule_type="loitering",
                                    track_id=track_id,
                                    dwell_time_s=dwell,
                                )
                            )
                    continue

                if zone.rule_type == "stopped_vehicle" and inside:
                    if not was_inside:
                        state.zone_entered_at[zone.zone_id] = now_s
                    speed = state.speed()
                    dwell = now_s - state.zone_entered_at.get(zone.zone_id, now_s)
                    key = (zone.zone_id, "stopped_vehicle")
                    if (
                        speed is not None
                        and speed < zone.stopped_speed_threshold
                        and dwell >= zone.dwell_threshold_s
                        and key not in state.fired_rules
                    ):
                        state.fired_rules.add(key)
                        events.append(
                            ZoneEvent(
                                zone_id=zone.zone_id,
                                zone_name=zone.name,
                                rule_type="stopped_vehicle",
                                track_id=track_id,
                                dwell_time_s=dwell,
                            )
                        )
                    elif speed is not None and speed >= zone.stopped_speed_threshold:
                        state.fired_rules.discard(key)
                    continue

                if zone.rule_type == "wrong_way" and inside:
                    heading = state.heading_deg()
                    key = (zone.zone_id, "wrong_way")
                    if heading is not None:
                        delta = abs((heading - zone.expected_direction_deg + 180) % 360 - 180)
                        if delta > zone.direction_tolerance_deg:
                            if key not in state.fired_rules:
                                state.fired_rules.add(key)
                                events.append(
                                    ZoneEvent(
                                        zone_id=zone.zone_id,
                                        zone_name=zone.name,
                                        rule_type="wrong_way",
                                        track_id=track_id,
                                        heading_deg=heading,
                                    )
                                )
                        else:
                            state.fired_rules.discard(key)
                    continue

        return events
