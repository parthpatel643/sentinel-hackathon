#!/usr/bin/env python3
"""Chaos drills — docs/05-DELIVERY-PLAN.md M15: "kill feeds, block 8554,
force loop cuts, throttle the network — during a rehearsed demo".

The point of this script is that resilience claims in the HLD are *checked*
rather than asserted. Each drill breaks something real about the running
stack, watches the platform's own API to see whether it noticed and
recovered, and records the actual timings. A drill that cannot be run
honestly on this machine is reported as SKIPPED with the reason and the
exact command that would run it elsewhere — never silently passed.

Usage:
    uv run python scripts/chaos_drill.py --list
    uv run python scripts/chaos_drill.py --drill feed-loss
    uv run python scripts/chaos_drill.py --all --report evidence/M15-CHAOS-DRILLS.md

Preconditions: the synthetic grid must be publishing (`scripts/synthetic_grid.py
start`) and an edge worker must be running against it (`--source synthetic`),
because the drills observe camera health that only a live worker reports.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
GRID_DIR = REPO_ROOT / "var" / "synthetic-grid"
PIDS_PATH = GRID_DIR / "pids.json"

CORE_API_URL = os.environ.get("SENTINEL_CORE_API_URL", "http://localhost:18000")
RELAY_API_URL = os.environ.get("SENTINEL_RELAY_API_URL", "http://127.0.0.1:9997")
RELAY_HLS_URL = os.environ.get("SENTINEL_RELAY_HLS_URL", "http://127.0.0.1:8888")
RELAY_RTSP_HOST = "127.0.0.1"
RELAY_RTSP_PORT = 8554

ADMIN_EMAIL = os.environ.get("SENTINEL_ADMIN_EMAIL", "admin@sentinel-platform.com")
ADMIN_PASSWORD = os.environ.get("SENTINEL_ADMIN_PASSWORD", "sentinel-admin-2026")

# How long the scene-cut drill waits for a feed to reach its own loop point.
# Generous, because when the cut happens is the feed's choice, not ours.
SCENE_CUT_WATCH_S = float(os.environ.get("SENTINEL_SCENE_CUT_WATCH_S", 600))


@dataclass
class DrillResult:
    """One drill's outcome. `observations` is an ordered log of what was
    actually seen, with elapsed seconds — this is the evidence, not the
    PASS/FAIL flag on its own."""

    name: str
    outcome: str  # PASS | FAIL | SKIPPED
    summary: str
    observations: list[str] = field(default_factory=list)
    started_at: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "outcome": self.outcome,
            "summary": self.summary,
            "observations": self.observations,
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 1),
        }


class Console:
    """Minimal structured output. Drills are watched live during a rehearsal,
    so each step prints as it happens rather than only at the end."""

    def __init__(self) -> None:
        self._t0 = time.monotonic()

    def reset(self) -> None:
        self._t0 = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self._t0

    def step(self, message: str) -> str:
        line = f"[{self.elapsed():6.1f}s] {message}"
        print(line, flush=True)
        return line


console = Console()


def _login() -> str:
    response = httpx.post(
        f"{CORE_API_URL}/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10.0,
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


def _get_camera(token: str, camera_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"{CORE_API_URL}/api/v1/cameras/{camera_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def _wait_for_camera(
    token: str,
    camera_id: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout_s: float,
    poll_s: float = 2.0,
) -> tuple[bool, dict[str, Any] | None]:
    """Poll the platform's own camera API until `predicate` holds. Returns
    the camera payload that satisfied it, so the caller can record the real
    observed values rather than re-fetching (and possibly seeing a different
    state)."""
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = _get_camera(token, camera_id)
        except httpx.HTTPError:
            time.sleep(poll_s)
            continue
        if predicate(last):
            return True, last
        time.sleep(poll_s)
    return False, last


def _read_grid_pids() -> dict[str, int]:
    if not PIDS_PATH.exists():
        return {}
    pids: dict[str, int] = json.loads(PIDS_PATH.read_text())
    return pids


def _write_grid_pids(pids: dict[str, int]) -> None:
    PIDS_PATH.write_text(json.dumps(pids, indent=2))


def _publisher_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _restart_publisher(camera_id: str) -> int:
    """Republish one synthetic camera, mirroring scripts/synthetic_grid.py's
    own ffmpeg invocation. Imported rather than duplicated so the two can
    never drift into publishing different things."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import synthetic_grid  # type: ignore[import-not-found]

    cam = next(c for c in synthetic_grid.CAMERAS if c.camera_id == camera_id)
    ffmpeg = synthetic_grid._require_ffmpeg()
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "warning",
        "-re", "-stream_loop", "-1",
        "-i", str(cam.clip_path),
        "-c", "copy",
        "-rtsp_transport", "tcp",
        "-f", "rtsp", cam.publish_url,
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.pid


def _pick_live_camera(token: str, *, external: bool = False) -> str | None:
    """Pick a live camera to act on.

    `external=False` (default) restricts to synthetic dev cameras this
    machine publishes, because the drills that kill a publisher must never
    act on a real government camera. `external=True` asks for the opposite —
    a real feed — for drills that need behaviour our fixture cannot produce.
    """
    response = httpx.get(
        f"{CORE_API_URL}/api/v1/cameras",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    pids = _read_grid_pids()
    for camera in response.json():
        if camera["status"] != "live":
            continue
        is_synthetic = camera["camera_id"] in pids
        if is_synthetic is not external:
            camera_id: str = camera["camera_id"]
            return camera_id
    return None


def _external_discontinuities(token: str) -> dict[str, int]:
    """Current discontinuity count for every live external camera, keyed by id."""
    response = httpx.get(
        f"{CORE_API_URL}/api/v1/cameras",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    pids = _read_grid_pids()
    return {
        camera["camera_id"]: camera.get("discontinuities") or 0
        for camera in response.json()
        if camera["status"] == "live" and camera["camera_id"] not in pids
    }


# --- Drill 1: feed loss -----------------------------------------------------


def drill_feed_loss(token: str) -> DrillResult:
    """'Feeds are supervised and may restart. Expect occasional brief
    interruptions.' Kills one camera's publisher outright and checks the
    platform both notices (status leaves `live`) and recovers on its own
    once the feed returns — including counting the reconnect."""
    console.reset()
    result = DrillResult(
        name="feed-loss",
        outcome="FAIL",
        summary="",
        started_at=datetime.now(UTC).isoformat(),
    )

    camera_id = _pick_live_camera(token)
    if camera_id is None:
        result.outcome = "SKIPPED"
        result.summary = (
            "No live synthetic camera found. Start the grid "
            "(`uv run python scripts/synthetic_grid.py start`) and an edge worker "
            "(`--source synthetic`) first."
        )
        result.observations.append(console.step(result.summary))
        return result

    pids = _read_grid_pids()
    pid = pids[camera_id]
    baseline = _get_camera(token, camera_id)
    baseline_reconnects = baseline.get("reconnects", 0)
    result.observations.append(
        console.step(
            f"baseline: {camera_id} status={baseline['status']} "
            f"reconnects={baseline_reconnects} fps={baseline.get('measured_fps')}"
        )
    )

    os.kill(pid, signal.SIGTERM)
    result.observations.append(console.step(f"killed publisher for {camera_id} (pid {pid})"))

    noticed, observed = _wait_for_camera(
        token, camera_id, lambda c: c["status"] != "live", timeout_s=90
    )
    if not noticed:
        result.summary = (
            f"{camera_id} never left `live` within 90s of its feed being killed — "
            "the platform did not notice the outage."
        )
        result.observations.append(console.step(result.summary))
        _restart_publisher(camera_id)
        return result
    assert observed is not None
    detect_s = console.elapsed()
    result.observations.append(
        console.step(f"platform noticed: status={observed['status']} after {detect_s:.1f}s")
    )

    new_pid = _restart_publisher(camera_id)
    pids[camera_id] = new_pid
    _write_grid_pids(pids)
    result.observations.append(console.step(f"republished {camera_id} (pid {new_pid})"))

    recovered, observed = _wait_for_camera(
        token, camera_id, lambda c: c["status"] == "live", timeout_s=180
    )
    if not recovered or observed is None:
        result.summary = f"{camera_id} did not return to `live` within 180s of the feed returning."
        result.observations.append(console.step(result.summary))
        return result

    result.observations.append(
        console.step(
            f"recovered: status=live reconnects={observed.get('reconnects')} "
            f"fps={observed.get('measured_fps')} after {console.elapsed():.1f}s total"
        )
    )
    if observed.get("reconnects", 0) <= baseline_reconnects:
        result.summary = (
            f"{camera_id} returned to `live` but its reconnect counter did not increase "
            f"({baseline_reconnects} -> {observed.get('reconnects')}) — the recovery was "
            "not attributed to a real reconnect."
        )
        result.observations.append(console.step(result.summary))
        return result

    result.outcome = "PASS"
    result.summary = (
        f"{camera_id} left `live` {detect_s:.0f}s after its feed was killed, then recovered "
        f"to `live` unattended once the feed returned, with the reconnect counted "
        f"({baseline_reconnects} -> {observed.get('reconnects')})."
    )
    result.observations.append(console.step(result.summary))
    return result


# --- Drill 2: RTSP (8554) blocked ------------------------------------------


def drill_rtsp_blocked(token: str) -> DrillResult:
    """'If port 8554 is blocked on your network, use the HLS endpoint
    instead.' Proves the fallback is a real capability of our own capture
    layer, not a line in a document: the same capture class that reads RTSP
    is pointed at the HLS URL and must return decoded frames.

    Deliberately does NOT disable the relay's RTSP listener. The scenario in
    the guide is a *client-side* block — the camera and gateway are fine, our
    network can't reach 8554 — so the honest test is whether our consumer can
    fall back, not whether the relay survives losing its publishers.
    """
    console.reset()
    result = DrillResult(
        name="rtsp-blocked",
        outcome="FAIL",
        summary="",
        started_at=datetime.now(UTC).isoformat(),
    )

    camera_id = _pick_live_camera(token)
    if camera_id is None:
        result.outcome = "SKIPPED"
        result.summary = "No live synthetic camera to read. Start the grid and an edge worker."
        result.observations.append(console.step(result.summary))
        return result

    # Confirm 8554 is genuinely reachable right now, so a later failure to
    # reach a blocked port means something.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(3.0)
        reachable = probe.connect_ex((RELAY_RTSP_HOST, RELAY_RTSP_PORT)) == 0
    result.observations.append(
        console.step(f"baseline: RTSP {RELAY_RTSP_HOST}:{RELAY_RTSP_PORT} reachable={reachable}")
    )
    if not reachable:
        result.outcome = "SKIPPED"
        result.summary = "RTSP port 8554 was already unreachable; nothing to compare against."
        result.observations.append(console.step(result.summary))
        return result

    # Simulate the block by pointing the capture at a port nothing listens on.
    blocked_port = _find_closed_port()
    blocked_url = f"rtsp://{RELAY_RTSP_HOST}:{blocked_port}/dev/{camera_id}"
    hls_url = f"{RELAY_HLS_URL}/dev/{camera_id}/index.m3u8"

    from edge_agent.pipeline.capture import CaptureConfig, RtspCapture

    blocked_capture = RtspCapture(config=CaptureConfig(camera_id=camera_id, url=blocked_url))
    opened_blocked = blocked_capture.open()
    blocked_capture.close()
    result.observations.append(
        console.step(f"with 8554 blocked (simulated via closed port {blocked_port}): "
                     f"RTSP open succeeded={opened_blocked}")
    )
    if opened_blocked:
        result.summary = (
            "The RTSP capture reported success against a port nothing is listening on — "
            "the blocked-port precondition is not actually being exercised."
        )
        result.observations.append(console.step(result.summary))
        return result

    hls_capture = RtspCapture(config=CaptureConfig(camera_id=camera_id, url=hls_url))
    if not hls_capture.open():
        result.summary = f"HLS fallback failed to open {hls_url} while RTSP was blocked."
        result.observations.append(console.step(result.summary))
        hls_capture.close()
        return result

    frames = 0
    deadline = time.monotonic() + 20.0
    while frames < 5 and time.monotonic() < deadline:
        if hls_capture.read() is not None:
            frames += 1
    hls_capture.close()
    result.observations.append(
        console.step(f"HLS fallback opened {hls_url} and decoded {frames} frame(s)")
    )

    if frames < 5:
        result.summary = (
            f"HLS fallback opened but only decoded {frames}/5 frames in 20s — "
            "not a usable fallback."
        )
        result.observations.append(console.step(result.summary))
        return result

    result.outcome = "PASS"
    result.summary = (
        f"With RTSP unreachable, the same capture layer opened the HLS endpoint for "
        f"{camera_id} and decoded {frames} frames — the documented fallback works."
    )
    result.observations.append(console.step(result.summary))
    return result


def _find_closed_port() -> int:
    """Bind a port, learn its number, release it. Briefly racy by nature, but
    good enough to stand in for 'nothing is listening here'."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((RELAY_RTSP_HOST, 0))
        port: int = sock.getsockname()[1]
    return port


# --- Drill 3: scene discontinuity (loop cut) --------------------------------


def drill_scene_cut(token: str) -> DrillResult:
    """'Each feed is a continuous recording that loops. At the loop point the
    scene cuts abruptly, similar to a camera reboot. Long-lived state should
    recover from a hard cut.'

    This drill deliberately refuses to run against the synthetic grid. That
    fixture provably cannot produce the condition: ffmpeg's `-stream_loop`
    renumbers timestamps to be seamless across loop iterations, so its PTS
    never discontinues (measured and written up in
    `evidence/M2-SYNTHETIC-GRID-DISCONTINUITY-FINDING.md`). Restarting a
    publisher does not stand in for it either — a fresh process is a
    connection drop and reconnect, which is what the `feed-loss` drill
    already covers. Passing this drill on a restart would be claiming
    evidence the run did not produce.

    So: it watches a *real* external feed for a genuine discontinuity and,
    when one occurs, checks the platform kept analysing across it.
    """
    console.reset()
    result = DrillResult(
        name="scene-cut",
        outcome="FAIL",
        summary="",
        started_at=datetime.now(UTC).isoformat(),
    )

    camera_id = _pick_live_camera(token, external=True)
    if camera_id is None:
        result.outcome = "SKIPPED"
        result.summary = (
            "No live external (e.g. government) camera to watch. The synthetic grid cannot "
            "produce a PTS discontinuity at all — see "
            "evidence/M2-SYNTHETIC-GRID-DISCONTINUITY-FINDING.md — so running this against it "
            "would report a pass it did not earn. Start a worker with `--source gov` and "
            "re-run."
        )
        result.observations.append(console.step(result.summary))
        return result

    # Watch every live external camera, not just one: the loop point belongs to
    # the feed, so pinning the drill to a single camera makes catching a cut a
    # coin toss. An earlier run of this drill sat on one camera for 25 minutes
    # and saw nothing while the fleet as a whole recorded five discontinuities.
    baseline = _external_discontinuities(token)
    result.observations.append(
        console.step(
            f"watching {len(baseline)} live external camera(s) for a real loop-point cut: "
            + ", ".join(f"{cam}={count}" for cam, count in sorted(baseline.items()))
        )
    )

    deadline = time.monotonic() + SCENE_CUT_WATCH_S
    cut_camera: str | None = None
    while time.monotonic() < deadline and cut_camera is None:
        time.sleep(5.0)
        current = _external_discontinuities(token)
        for cam, count in current.items():
            if count > baseline.get(cam, 0):
                cut_camera = cam
                result.observations.append(
                    console.step(
                        f"real discontinuity observed on {cam} after {console.elapsed():.0f}s: "
                        f"{baseline.get(cam, 0)} -> {count}"
                    )
                )
                break

    if cut_camera is None:
        result.outcome = "SKIPPED"
        result.summary = (
            f"No discontinuity occurred on any live external camera within "
            f"{SCENE_CUT_WATCH_S / 60:.0f} minutes. Inconclusive rather than a failure — "
            "the loop point is the feed's to choose, not ours. Re-run for longer to catch one."
        )
        result.observations.append(console.step(result.summary))
        return result

    # The cut must not wedge the camera: it has to still be analysing, with a
    # real frame rate rather than a stale last value.
    still_running, after = _wait_for_camera(
        token,
        cut_camera,
        lambda c: c["status"] == "live" and (c.get("measured_fps") or 0) > 0,
        timeout_s=120,
        poll_s=5.0,
    )
    if not still_running or after is None:
        result.summary = (
            f"{cut_camera} stopped analysing after a scene cut (status/measured_fps did not "
            "recover within 120s) — long-lived state did not survive the cut."
        )
        result.observations.append(console.step(result.summary))
        return result

    result.outcome = "PASS"
    result.summary = (
        f"{cut_camera} absorbed a real PTS discontinuity at its loop point "
        f"(discontinuities {baseline.get(cut_camera, 0)} -> {after.get('discontinuities')}) and "
        f"kept analysing ({after.get('measured_fps')} fps), without operator action."
    )
    result.observations.append(console.step(result.summary))
    return result


# --- Drill 4: network throttle ---------------------------------------------


def drill_network_throttle(token: str) -> DrillResult:
    """Bandwidth shaping on macOS needs `pfctl`/`dnctl`, which need root.
    Rather than fake it, this reports SKIPPED with the exact commands, so the
    drill is reproducible by someone who can run it — and is never counted as
    a pass it did not earn."""
    console.reset()
    result = DrillResult(
        name="network-throttle",
        outcome="SKIPPED",
        summary="",
        started_at=datetime.now(UTC).isoformat(),
    )
    if os.geteuid() != 0:
        result.summary = (
            "Requires root: macOS bandwidth shaping goes through pfctl/dnctl. Not simulated "
            "in-process, because throttling the application rather than the link would test "
            "something else entirely and the result would not mean what it claims."
        )
        result.observations.append(console.step(result.summary))
        result.observations.append(
            console.step(
                "To run manually: `sudo dnctl pipe 1 config bw 500Kbit/s` then pipe port "
                f"{RELAY_RTSP_PORT} traffic into it via an anchor in /etc/pf.conf, re-run the "
                "worker, and confirm cameras degrade rather than crash. "
                "`sudo dnctl -q flush` to restore."
            )
        )
        return result

    result.summary = (
        "Running as root, but automated pf anchor manipulation is deliberately not implemented: "
        "it rewrites system firewall state and a failed restore would leave this machine's "
        "networking broken. Run the documented commands manually instead."
    )
    result.observations.append(console.step(result.summary))
    return result


DRILLS: dict[str, Callable[[str], DrillResult]] = {
    "feed-loss": drill_feed_loss,
    "rtsp-blocked": drill_rtsp_blocked,
    "scene-cut": drill_scene_cut,
    "network-throttle": drill_network_throttle,
}


def _render_report(results: list[DrillResult]) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    counts = {
        outcome: sum(1 for r in results if r.outcome == outcome)
        for outcome in ("PASS", "FAIL", "SKIPPED")
    }
    lines = [
        "# M15 Chaos Drills — results",
        "",
        f"Generated by `scripts/chaos_drill.py` on {now}.",
        "",
        f"**{counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIPPED']} skipped.**",
        "",
        "Each drill breaks something real about a running stack and then watches the",
        "platform's own API to see whether it noticed and recovered. A drill that could",
        "not be run honestly on this machine is recorded as SKIPPED with the reason —",
        "never as a pass.",
        "",
        "| Drill | Outcome | Summary |",
        "|---|---|---|",
    ]
    for r in results:
        lines.append(f"| `{r.name}` | **{r.outcome}** | {r.summary} |")
    lines.append("")
    for r in results:
        lines.extend(
            [
                f"## {r.name}",
                "",
                f"- **Outcome:** {r.outcome}",
                f"- **Started:** {r.started_at}",
                f"- **Duration:** {r.duration_s:.1f}s",
                "",
                "```",
                *r.observations,
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drill", choices=sorted(DRILLS), help="run a single drill")
    parser.add_argument("--all", action="store_true", help="run every drill in order")
    parser.add_argument("--list", action="store_true", help="list drills and exit")
    parser.add_argument("--report", type=Path, help="write a markdown report here")
    args = parser.parse_args()

    if args.list:
        for name, fn in DRILLS.items():
            summary = (fn.__doc__ or "").strip().splitlines()[0]
            print(f"{name:18} {summary}")
        return 0

    if not args.all and not args.drill:
        parser.error("pass --drill NAME, --all, or --list")

    selected = list(DRILLS) if args.all else [args.drill]

    try:
        token = _login()
    except httpx.HTTPError as exc:
        print(f"could not log in to core_api at {CORE_API_URL}: {exc}", file=sys.stderr)
        return 2

    results: list[DrillResult] = []
    for name in selected:
        assert name is not None
        print(f"\n=== drill: {name} ===", flush=True)
        started = time.monotonic()
        result = DRILLS[name](token)
        result.duration_s = time.monotonic() - started
        results.append(result)
        print(f"--- {name}: {result.outcome} ---", flush=True)

    print("\n=== summary ===")
    for result in results:
        print(f"{result.outcome:8} {result.name:18} {result.summary}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_render_report(results))
        print(f"\nreport written to {args.report}")

    return 1 if any(r.outcome == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
