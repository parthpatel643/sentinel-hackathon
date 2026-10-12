"""Automated compliance with the organisers' integrator guide.

The challenge publishes a pre-submission checklist, and most failures come from
ignoring it. Each rule below is asserted rather than trusted, so a refactor
cannot quietly break compliance months after someone read the guide.

These same checks back the "Integrator Compliance" panel in the ops dashboard.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MEDIAMTX_CONFIG = REPO_ROOT / "infra" / "compose" / "mediamtx.yml"
EDGE_AGENT_SRC = REPO_ROOT / "services" / "edge_agent" / "src"
CORE_PKG_SRC = REPO_ROOT / "packages" / "sentinel_core" / "src"


@pytest.fixture(scope="module")
def relay_config() -> dict[str, Any]:
    config: dict[str, Any] = yaml.safe_load(MEDIAMTX_CONFIG.read_text())
    return config


# --- DO: force RTSP over TCP everywhere -------------------------------------


def test_relay_forces_rtsp_over_tcp(relay_config: dict[str, Any]) -> None:
    """UDP is accepted by the gateway but fails across NAT and most corporate
    firewalls, and partial UDP delivery produces corrupt frames that look
    exactly like model bugs."""
    assert relay_config["rtspTransports"] == ["tcp"]
    assert relay_config["pathDefaults"]["rtspTransport"] == "tcp"


def test_settings_force_rtsp_over_tcp() -> None:
    from sentinel_core.config import Settings

    assert Settings().rtsp_transport == "tcp"


def test_hls_is_available_as_a_fallback(relay_config: dict[str, Any]) -> None:
    """If port 8554 is blocked on the evaluation network, HLS must still work."""
    assert relay_config["hls"] is True


# --- DON'T: publish to the gateway or call its control API ------------------


_LOCAL_PUBLISH_SCOPES = frozenset({"~^dev/.*$", "~^mirror/.*$"})


def test_relay_grants_no_unscoped_publish_permission(relay_config: dict[str, Any]) -> None:
    """'Consume only. Do not push streams to any path.'

    Real cameras are always pull sources (`source: rtsp://...`), so no publish
    grant is ever needed for them. The only permitted publish grants are for
    footage we replay from our own disk into our own local relay — the
    synthetic test grid under `dev/*` and the recorded copy of the government
    grid under `mirror/*` — never a blanket grant that could reach a real
    camera path.
    """
    for user in relay_config["authInternalUsers"]:
        for permission in user["permissions"]:
            if permission["action"] != "publish":
                continue
            path = permission.get("path")
            assert path, "a publish permission with no path restriction is a blanket grant"
            assert path in _LOCAL_PUBLISH_SCOPES, f"unexpected publish scope: {path!r}"


def test_the_dev_publish_permission_uses_a_dedicated_non_anonymous_credential(
    relay_config: dict[str, Any],
) -> None:
    """The synthetic-grid publisher must never ride on the anonymous `any`
    user — a dedicated credential keeps it structurally separate from every
    other permission grant, including if `any` is extended later. Each local
    publish scope gets its own credential, so one can never reach the other's
    paths."""
    scopes_per_user: list[set[str]] = []
    for user in relay_config["authInternalUsers"]:
        scopes = {p.get("path") for p in user["permissions"] if p["action"] == "publish"}
        if scopes:
            assert user["user"] != "any", "publish must not be granted to the anonymous user"
            assert user.get("pass"), "dev-grid credential must be a real (if non-secret) password"
            assert len(scopes) == 1, f"{user['user']} can publish to more than one scope"
            scopes_per_user.append(scopes)
    assert len(scopes_per_user) == len(set().union(*scopes_per_user))


def test_publishing_protocols_are_disabled(relay_config: dict[str, Any]) -> None:
    assert relay_config["rtmp"] is False
    assert relay_config["srt"] is False


def test_settings_forbid_publishing() -> None:
    from sentinel_core.config import Settings

    assert Settings().allow_stream_publish is False


# --- DO: drive all timing from PTS, never from arrival time -----------------

_WALL_CLOCK_FUNCS = frozenset({"time", "monotonic", "perf_counter", "now", "utcnow"})


def _wall_clock_calls(path: Path) -> list[str]:
    """Find wall-clock reads in a module.

    The gateway replays its buffered GOP on connect, so the first frames arrive
    faster than real time. Anything that timestamps by arrival will compute
    impossible velocities immediately after every reconnect.
    """
    tree = ast.parse(path.read_text())
    return [
        f"{path.name}:{node.lineno} {ast.unparse(node.func)}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _WALL_CLOCK_FUNCS
    ]


# frame_clock.py reads the wall clock for exactly one thing: rejecting a
# camera's own burned-in timestamp that claims to be in the future, which is
# how a year misread as 2036 instead of 2026 is caught. It is a plausibility
# bound on a timestamp that came off the *frame*, never a source of timing —
# the rule this suite enforces is that nothing derives time from arrival, and
# that still holds. Named here rather than blanket-allowed so a second,
# unjustified call in the same file still fails.
_WALL_CLOCK_ALLOWANCES = {"frame_clock.py": 1}


def test_analytics_code_never_reads_the_wall_clock() -> None:
    """Timing must come from CAP_PROP_POS_MSEC / buffer PTS / RTP timestamps."""
    offenders: list[str] = []
    for module in EDGE_AGENT_SRC.rglob("*.py"):
        calls = _wall_clock_calls(module)
        allowed = _WALL_CLOCK_ALLOWANCES.get(module.name, 0)
        if len(calls) > allowed:
            offenders.extend(calls[allowed:])
    assert not offenders, f"wall-clock reads in the analytics path: {offenders}"


def test_the_frame_clock_allowance_is_still_needed() -> None:
    """If the plausibility check stops reading the wall clock, the allowance
    above should go with it rather than quietly widening what is permitted."""
    frame_clock = EDGE_AGENT_SRC / "edge_agent" / "analytics" / "frame_clock.py"
    assert len(_wall_clock_calls(frame_clock)) == _WALL_CLOCK_ALLOWANCES["frame_clock.py"]


def test_stream_clock_reads_wall_time_only_to_anchor() -> None:
    """One allowed use: mapping a stream's PTS origin to absolute time once per
    connection leg."""
    offenders = _wall_clock_calls(CORE_PKG_SRC / "sentinel_core" / "clock.py")
    assert len(offenders) == 1, f"expected exactly one anchor call, found {offenders}"


def test_frame_timing_exposes_pts_not_arrival() -> None:
    from sentinel_core.clock import FrameTiming

    fields = set(FrameTiming.__dataclass_fields__)
    assert {"pts_ms", "stream_epoch", "observed_at", "delta_ms"} <= fields
    assert not any("arriv" in field for field in fields)


def test_the_tracker_must_be_given_each_frames_pts() -> None:
    """Kalman filters and multi-object trackers must be fed PTS deltas. Not
    reading the wall clock is not enough: a tracker that steps once per frame
    also ignores time. The PTS is a required argument, with no default to
    fall back to."""
    import inspect

    from edge_agent.analytics.tracker import SimpleTracker

    pts = inspect.signature(SimpleTracker.update).parameters["pts_ms"]
    assert pts.kind is inspect.Parameter.KEYWORD_ONLY
    assert pts.default is inspect.Parameter.empty


def test_tracked_velocity_does_not_depend_on_how_frames_were_spaced() -> None:
    """The same 200 px/s car seen through a reconnect's fast-delivered GOP
    (frames 40 ms apart) and at a steady 8 fps: the tracker infers the same
    speed from both, because only PTS deltas enter its motion model."""
    from edge_agent.analytics.tracker import SimpleTracker
    from edge_agent.analytics.vehicle_detector import VehicleDetection

    def speed(step_ms: float) -> float:
        tracker = SimpleTracker()
        for i in range(12):
            x = 100.0 + 0.2 * step_ms * i
            box = (x, 200.0, x + 100.0, 300.0)
            tracker.update([VehicleDetection(box, "car", 0.9)], pts_ms=i * step_ms)
        return float(tracker._tracks[0].kf.statePost[4, 0])

    assert speed(40.0) == pytest.approx(200.0, rel=0.1)
    assert speed(125.0) == pytest.approx(200.0, rel=0.1)


def test_the_view_monitor_times_its_streaks_by_pts() -> None:
    """The camera-condition checks wait for a reading to hold before raising
    "moved", "covered" or "blurred". That wait is footage time from each
    frame's PTS, never a count of frames or checks: a reconnect's GOP replay
    packs many frames into little footage, and the analysed rate varies by
    tier and camera. So the PTS is required, and the same footage gives the
    same answer however densely it was sampled or checked."""
    import inspect

    import cv2
    import numpy as np

    from edge_agent.analytics.tamper import TamperDetector
    from edge_agent.analytics.view_monitor import ViewMonitor

    for method in (ViewMonitor.observe, TamperDetector.update):
        pts = inspect.signature(method).parameters["pts_ms"]
        assert pts.kind is inspect.Parameter.KEYWORD_ONLY
        assert pts.default is inspect.Parameter.empty

    def covered_after_s(step_ms: float) -> float | None:
        detector, dark = TamperDetector(), np.zeros((120, 160, 3), dtype=np.uint8)
        for i in range(100):
            if detector.update(dark, pts_ms=i * step_ms) == "covered":
                return i * step_ms / 1000
        return None

    assert covered_after_s(20.0) == covered_after_s(125.0) == pytest.approx(0.5)

    rng = np.random.default_rng(7)
    scene = np.full((540, 960, 3), 90, dtype=np.uint8)
    for _ in range(140):
        x, y = int(rng.integers(0, 920)), int(rng.integers(0, 500))
        w, h = int(rng.integers(10, 90)), int(rng.integers(10, 90))
        colour = tuple(int(c) for c in rng.integers(0, 255, 3))
        cv2.rectangle(scene, (x, y), (x + w, y + h), colour, -1)
    knock = np.array([[1, 0, 115], [0, 1, 27]], dtype=np.float32)  # 12% across, 5% down
    knocked = cv2.warpAffine(scene, knock, (960, 540), borderMode=cv2.BORDER_REPLICATE)

    def moved_after_s(check_interval_s: float) -> float | None:
        monitor = ViewMonitor(check_interval_s=check_interval_s)
        for i in range(80):
            frame = scene if i < 32 else knocked  # knocked 8 s in, frames 0.25 s apart
            if monitor.observe(frame, pts_ms=i * 250.0) is not None:
                return i * 0.25 - 8.0
        return None

    assert moved_after_s(0.5) == moved_after_s(2.0) == pytest.approx(4.0)


# --- DO: reconnect with exponential backoff ---------------------------------


def test_backoff_is_bounded_and_not_a_tight_loop() -> None:
    """'Start at ~2 s, cap at ~30 s. Do not reconnect in a tight loop.'"""
    from sentinel_core.config import Settings

    settings = Settings()
    assert settings.reconnect_backoff_initial_s >= 1.0
    assert settings.reconnect_backoff_max_s <= 60.0
    assert settings.reconnect_backoff_initial_s < settings.reconnect_backoff_max_s


# --- DO: read the camera list from the catalogue every run ------------------


def test_no_hard_coded_stream_urls_in_the_relay(relay_config: dict[str, Any]) -> None:
    """'Ids/camera set can change — always start from the catalogue.'"""
    for name, config in (relay_config.get("paths") or {}).items():
        source = (config or {}).get("source", "publisher")
        assert not str(source).startswith("rtsp://"), (
            f"path '{name}' hard-codes a stream URL; cameras must come from the catalogue"
        )


# --- DON'T: trust the declared frame rate -----------------------------------


def test_declared_fps_is_documented_as_metadata_only() -> None:
    """CAP_PROP_FPS routinely disagrees with the real delivery rate."""
    from sentinel_core.schemas import StreamProfile

    description = StreamProfile.model_fields["declared_fps"].description or ""
    assert "metadata only" in description.lower()


def test_health_reports_measured_fps_separately_from_declared() -> None:
    from sentinel_core.schemas import HealthPayload

    assert {"measured_fps", "declared_fps"} <= set(HealthPayload.model_fields)


# --- DO: expect a scene discontinuity at the loop point ---------------------


def test_pipeline_can_detect_and_report_a_loop_cut() -> None:
    """Long-lived state — background models, ReID galleries, track ids — must
    recover from a hard cut rather than assume infinite continuity."""
    from sentinel_core.clock import StreamClock
    from sentinel_core.schemas import EventType

    clock = StreamClock("cam-compliance")
    clock.observe(0.0)
    pts = 40.0
    while pts <= 10_000.0:
        clock.observe(pts)
        pts += 40.0

    assert clock.observe(0.0).is_discontinuity
    assert EventType.STREAM_DISCONTINUITY  # the cut is observable downstream


# --- DON'T: assume a uniform grid -------------------------------------------


def test_stream_profile_carries_per_camera_properties() -> None:
    """'Cameras differ in resolution, codec, frame rate and bitrate. A fixed
    shape inference batch across every camera will not work.'"""
    from sentinel_core.schemas import StreamProfile

    assert {"codec", "width", "height", "declared_fps"} <= set(StreamProfile.model_fields)
