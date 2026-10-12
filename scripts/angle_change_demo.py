#!/usr/bin/env python3
"""Demonstrate a camera-angle alert on recorded footage, with no hardware.

Republishes one mirrored government camera into the local relay as
`dev/angle-demo`, knocks its view part-way through (as wind, a vehicle or a
person would), and optionally puts it back later. The camera is registered in
the console, so the edge worker's view monitor sees it like any other:

    uv run python scripts/angle_change_demo.py start            # knock at 60 s, restore at 180 s
    make worker SOURCE=registry CAMERAS=angle-demo SAMPLED_FPS=2 # in another terminal
    uv run python scripts/angle_change_demo.py stop

The replay starts 300 s into the recording by default: the mirrored clips
were stitched from overlapping captures, and before that point cam01's
burned-in clock jumps backwards. The camera's clock is the only time shown,
so the demo plays a stretch where it runs straight (knock ≈ 21:06:3x,
restore ≈ 21:08:3x on cam01).

Run the worker at the same sampled rate as the main one (`SAMPLED_FPS=2` on
a laptop): at 8 fps a second worker falls behind live and alerts arrive late.

What to expect: the worker learns the normal view in a few seconds; about 6 s
after the knock a "Camera view changed" banner appears on every open console,
and Alerts → Camera views shows the remembered view beside the view now with
how far it moved. When the view is restored, the alert closes itself.

On the day, a real camera turned by hand (or a phone running an RTSP camera
app, onboarded by CSV) shows the same thing live.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
from pathlib import Path

import httpx

from sentinel_core.config import get_settings

REPO = Path(__file__).resolve().parents[1]
CLIPS = REPO / "data" / "gov-mirror" / "clips"
STATE = REPO / "var" / "angle-demo.pid"
CAMERA_ID = "angle-demo"
PUBLISH_URL = "rtsp://dev-grid:dev-grid-local-only@127.0.0.1:8554/dev/angle-demo"
READ_URL = "rtsp://127.0.0.1:8554/dev/angle-demo"


def _crop_filter(knock_at: float, restore_at: float, shift: float) -> str:
    """An 80% window of the frame that jumps by `shift` of the width (and
    half that down) between the knock and the restore, scaled back to 720p —
    the picture a camera nudged on its mount actually produces. The camera's
    burned-in clock is laid back over the top-left corner from the unmoved
    frame, because a real camera's clock stays put when the camera moves."""
    until = f"t,{knock_at},{restore_at}" if restore_at > 0 else f"t,{knock_at},1e9"
    dx = f"if(between({until}),iw*{0.02 + shift:.3f},iw*0.02)"
    dy = f"if(between({until}),ih*{0.02 + shift / 2:.3f},ih*0.02)"
    return (
        "split[scene][osd];"
        f"[scene]crop=iw*0.8:ih*0.8:x='{dx}':y='{dy}',scale=1280:720[view];"
        "[osd]scale=1280:720,crop=iw*0.5:ih*0.075:0:0[clock];"
        "[view][clock]overlay=0:0"
    )


def _register(settings_token: str, api: str) -> None:
    body = {
        "camera_id": CAMERA_ID,
        "name": "Chiman Bhai Bridge · angle-change demo",
        "driver_id": "rtsp",
        "department_name": "Police",
        "site_name": "Demonstration",
        "location": {"lat": 23.0305, "lon": 72.5805},
        "tier": "b_sampled",
        "attributes": {"source": "angle_change_demo"},
        "profiles": [{"protocol": "rtsp", "url": READ_URL, "codec": "h264", "width": 1280}],
    }
    response = httpx.post(
        f"{api}/api/v1/cameras", json=body, headers={"X-Service-Token": settings_token}, timeout=10
    )
    if response.status_code not in (200, 201, 409):
        raise SystemExit(
            f"could not register {CAMERA_ID}: HTTP {response.status_code} {response.text}"
        )


def start(args: argparse.Namespace) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg not found on PATH (brew install ffmpeg)")
    clip = CLIPS / f"{args.camera}.mp4"
    if not clip.is_file():
        raise SystemExit(f"no recorded clip at {clip} — run `make mirror` first")
    stop(args, quiet=True)
    settings = get_settings()
    _register(settings.edge_service_token.get_secret_value(), settings.core_api_url)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-re", "-stream_loop", "-1",
        "-ss", f"{args.start_at:.0f}", "-i", str(clip),
        "-filter_complex", _crop_filter(args.knock_at, args.restore_at, args.shift),
        "-an", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-g", "50",
        "-f", "rtsp", "-rtsp_transport", "tcp", PUBLISH_URL,
    ]  # fmt: skip
    STATE.parent.mkdir(parents=True, exist_ok=True)
    log = STATE.with_suffix(".log")
    with log.open("wb") as log_file:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    STATE.write_text(str(process.pid))
    restore = f", restored at {args.restore_at:.0f} s" if args.restore_at > 0 else ""
    print(
        f"publishing {args.camera} as rtsp://127.0.0.1:8554/dev/{CAMERA_ID} "
        f"(pid {process.pid}): knocked {args.shift * 100:.0f}% at {args.knock_at:.0f} s{restore}.\n"
        f"ffmpeg log: {log}\n"
        f"Now run:  make worker SOURCE=registry CAMERAS={CAMERA_ID} SAMPLED_FPS=2"
    )


def stop(_args: argparse.Namespace, *, quiet: bool = False) -> None:
    if not STATE.is_file():
        if not quiet:
            print("not running")
        return
    pid = int(STATE.read_text())
    try:
        os.killpg(pid, signal.SIGTERM)
        if not quiet:
            print(f"stopped (pid {pid})")
    except ProcessLookupError:
        pass
    STATE.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    start_cmd = sub.add_parser("start", help="publish the demo camera and register it")
    start_cmd.add_argument(
        "--camera", default="cam01", help="mirrored camera to replay (default cam01)"
    )
    start_cmd.add_argument(
        "--start-at",
        type=float,
        default=300.0,
        help="seconds into the recording to start from (default 300: cam01's clock runs straight)",
    )
    start_cmd.add_argument("--knock-at", type=float, default=60.0, help="seconds into the stream")
    start_cmd.add_argument("--restore-at", type=float, default=180.0, help="0 = never put back")
    start_cmd.add_argument("--shift", type=float, default=0.12, help="fraction of the frame width")
    start_cmd.set_defaults(func=start)
    sub.add_parser("stop", help="stop publishing").set_defaults(func=stop)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
