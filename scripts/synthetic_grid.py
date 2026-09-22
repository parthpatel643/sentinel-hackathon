#!/usr/bin/env python3
"""Synthetic RTSP test grid.

Generates a small, mixed-codec, mixed-resolution set of looping test streams and
publishes them into the LOCAL, self-hosted MediaMTX relay under `dev/*` — never
the government gateway. This lets us develop and chaos-test (loop cuts, mixed
H.264/H.265, mixed resolutions, backoff, PTS correctness) without touching their
infrastructure or waiting on network access, exactly as recommended in
docs/01-ARCHITECTURE.md section 12.

Usage:
    uv run python scripts/synthetic_grid.py generate   # build the clips + catalogue
    uv run python scripts/synthetic_grid.py start       # loop-publish them into MediaMTX
    uv run python scripts/synthetic_grid.py status      # check what the relay sees
    uv run python scripts/synthetic_grid.py stop        # tear down the publishers
    uv run python scripts/synthetic_grid.py all         # generate + start
"""

from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRID_DIR = REPO_ROOT / "var" / "synthetic-grid"
CATALOGUE_PATH = GRID_DIR / "catalogue.json"
PIDS_PATH = GRID_DIR / "pids.json"

RELAY_RTSP_HOST = "127.0.0.1"
RELAY_RTSP_PORT = 8554
RELAY_API_URL = "http://127.0.0.1:9997"

# Matches the dev/*-only credential in infra/compose/mediamtx.yml. Not a
# secret — a throwaway local-fixture login, path-scoped so it can never touch
# a real camera path.
RELAY_PUBLISH_USER = "dev-grid"
RELAY_PUBLISH_PASS = "dev-grid-local-only"

# Short clips are deliberate: a benchmark run of a minute or two should see
# several loop cuts per camera, exercising the discontinuity path the
# organisers' guide calls out — not just the happy-path steady state.
CLIP_DURATION_S = 12


@dataclass(frozen=True, slots=True)
class SyntheticCamera:
    """Mirrors sentinel_core.schemas.CameraDescriptor closely enough that the
    grid's catalogue.json validates against the real model directly."""

    camera_id: str
    width: int
    height: int
    codec: str  # "h264" | "h265"
    fps: int
    tier: str
    department: str = "Development"

    @property
    def encoder(self) -> str:
        return {"h264": "libx264", "h265": "libx265"}[self.codec]

    @property
    def clip_path(self) -> Path:
        return GRID_DIR / f"{self.camera_id}.mp4"

    @property
    def publish_path(self) -> str:
        return f"dev/{self.camera_id}"

    @property
    def rtsp_url(self) -> str:
        """Consumer-facing URL. Read/playback are anonymous, so this is what
        goes into the catalogue and what capture clients actually use."""
        return f"rtsp://{RELAY_RTSP_HOST}:{RELAY_RTSP_PORT}/{self.publish_path}"

    @property
    def publish_url(self) -> str:
        """Only ffmpeg's push side uses this — carries the dev/*-scoped
        publish credential, which is never given to a consumer."""
        return (
            f"rtsp://{RELAY_PUBLISH_USER}:{RELAY_PUBLISH_PASS}@"
            f"{RELAY_RTSP_HOST}:{RELAY_RTSP_PORT}/{self.publish_path}"
        )


# Deliberately heterogeneous: two resolutions per tier band, both codecs, and
# frame rates that do not all divide evenly into each other — this is what
# "mixed grid" means in the organisers' Do/Don't list.
CAMERAS: list[SyntheticCamera] = [
    SyntheticCamera("dev-cam-01", 1920, 1080, "h264", 25, "a_continuous"),
    SyntheticCamera("dev-cam-02", 1920, 1080, "h265", 25, "a_continuous"),
    SyntheticCamera("dev-cam-03", 1280, 720, "h264", 15, "b_sampled"),
    SyntheticCamera("dev-cam-04", 1280, 720, "h265", 12, "b_sampled"),
    SyntheticCamera("dev-cam-05", 640, 480, "h264", 10, "c_motion_gated"),
    SyntheticCamera("dev-cam-06", 1920, 1080, "h264", 30, "a_continuous"),
    SyntheticCamera("dev-cam-07", 960, 540, "h265", 20, "b_sampled"),
    SyntheticCamera("dev-cam-08", 640, 360, "h264", 8, "c_motion_gated"),
]


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print("ffmpeg not found on PATH. Install it (e.g. `brew install ffmpeg`).", file=sys.stderr)
        raise SystemExit(1)
    return ffmpeg


def generate(*, force: bool = False) -> None:
    """Encode each synthetic camera's looping test clip."""
    ffmpeg = _require_ffmpeg()
    GRID_DIR.mkdir(parents=True, exist_ok=True)

    for cam in CAMERAS:
        if cam.clip_path.exists() and not force:
            print(f"skip  {cam.camera_id} (already generated)")
            continue

        print(f"build {cam.camera_id}  {cam.width}x{cam.height} {cam.codec} @ {cam.fps}fps")
        # testsrc renders a moving pattern with a native scrolling timestamp —
        # no libfreetype/drawtext dependency needed to verify PTS visually.
        pattern = f"testsrc=size={cam.width}x{cam.height}:rate={cam.fps}:duration={CLIP_DURATION_S}"
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi",
            "-i", pattern,
            "-c:v", cam.encoder,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(cam.clip_path),
        ]  # fmt: skip
        subprocess.run(cmd, check=True)

    _write_catalogue()


def _write_catalogue() -> None:
    """Write catalogue.json in the exact shape of CameraDescriptor.

    Validated before writing so a mistake here fails loudly instead of
    surfacing later as a confusing parse error in the catalogue client.
    """
    sys.path.insert(0, str(REPO_ROOT / "packages" / "sentinel_core" / "src"))
    from sentinel_core.schemas import CameraDescriptor

    entries = []
    for cam in CAMERAS:
        descriptor = CameraDescriptor.model_validate(
            {
                "camera_id": cam.camera_id,
                "name": f"Synthetic {cam.camera_id} ({cam.width}x{cam.height} {cam.codec}"
                f"@{cam.fps})",
                "driver_id": "rtsp",
                "department": cam.department,
                "site": "Local Synthetic Grid",
                "location": {"lat": 23.0225, "lon": 72.5714},
                "profiles": [
                    {
                        "protocol": "rtsp",
                        "url": cam.rtsp_url,
                        "codec": cam.codec,
                        "width": cam.width,
                        "height": cam.height,
                        "declared_fps": cam.fps,
                    }
                ],
                "tier": cam.tier,
            }
        )
        entries.append(descriptor.model_dump(mode="json"))

    CATALOGUE_PATH.write_text(json.dumps(entries, indent=2))
    print(f"catalogue written to {CATALOGUE_PATH} ({len(entries)} cameras)")


def start() -> None:
    """Loop-publish every generated clip into the relay's dev/* paths."""
    ffmpeg = _require_ffmpeg()
    missing = [cam.camera_id for cam in CAMERAS if not cam.clip_path.exists()]
    if missing:
        print(f"missing clips: {missing}. Run `generate` first.", file=sys.stderr)
        raise SystemExit(1)

    pids: dict[str, int] = {}
    for cam in CAMERAS:
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "warning",
            "-re", "-stream_loop", "-1",
            "-i", str(cam.clip_path),
            "-c", "copy",
            "-rtsp_transport", "tcp",
            "-f", "rtsp", cam.publish_url,
        ]  # fmt: skip
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pids[cam.camera_id] = proc.pid
        print(f"publish {cam.camera_id} -> {cam.rtsp_url} (pid {proc.pid})")

    PIDS_PATH.write_text(json.dumps(pids, indent=2))
    print("waiting for the relay to pick up the first streams...")
    time.sleep(3)
    status()


def stop() -> None:
    if not PIDS_PATH.exists():
        print("no running synthetic grid found")
        return
    pids: dict[str, int] = json.loads(PIDS_PATH.read_text())
    for camera_id, pid in pids.items():
        try:
            import os

            os.kill(pid, signal.SIGTERM)
            print(f"stopped {camera_id} (pid {pid})")
        except ProcessLookupError:
            print(f"{camera_id} (pid {pid}) already gone")
    PIDS_PATH.unlink(missing_ok=True)


def status() -> None:
    import httpx

    try:
        response = httpx.get(f"{RELAY_API_URL}/v3/paths/list", timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"could not reach the relay API: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    live_paths = {item["name"] for item in response.json()["items"]}
    for cam in CAMERAS:
        marker = "\u2713 live" if cam.publish_path in live_paths else "\u2717 not publishing"
        print(f"  {cam.camera_id:14s} {cam.publish_path:20s} {marker}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="encode the synthetic clips + write the catalogue")
    gen.add_argument("--force", action="store_true", help="regenerate even if clips exist")
    sub.add_parser("start", help="loop-publish clips into the relay")
    sub.add_parser("stop", help="stop the publishers")
    sub.add_parser("status", help="show which dev/* paths the relay sees")
    all_cmd = sub.add_parser("all", help="generate then start")
    all_cmd.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.command == "generate":
        generate(force=args.force)
    elif args.command == "start":
        start()
    elif args.command == "stop":
        stop()
    elif args.command == "status":
        status()
    elif args.command == "all":
        generate(force=args.force)
        start()


if __name__ == "__main__":
    main()
