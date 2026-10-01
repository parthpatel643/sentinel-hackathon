#!/usr/bin/env python3
"""Measure what one machine sustains, per analytics tier, end to end.

`scripts/bench_capacity.py` measures decode alone. This measures the real
thing: N 1080p25 streams of a vehicle crossing the frame, published on the
local relay's `dev/` paths (never the government gateway, whose watch-time
quota is account-wide), registered in the registry with a chosen tier, and
analysed by the real registry-driven worker (`--source registry`). The
figures come back through the API the operator console reads: analysed fps,
analysis lag and status per camera, plus the worker's CPU.

Needs `make up` and `make api` running, ffmpeg, and the admin account
(`make seed`). Every camera it registers is called `load-...` and is deleted
again at the end of each run, detections included.

Usage:
    uv run --package core_api python scripts/measure_tier_capacity.py \\
        --tier b_sampled --cameras 4 8 12 --duration 90
    uv run --package core_api python scripts/measure_tier_capacity.py \\
        --tier a_continuous --stride 3 --cameras 1 2
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIP = REPO_ROOT / "var" / "load-grid" / "vehicle-1080p25.mp4"
SOURCE_IMAGE = REPO_ROOT / "var" / "test-images" / "plate.png"
VEHICLE_IMAGE = REPO_ROOT / "var" / "load-grid" / "vehicle-gj.png"
# The test image's own plate is foreign and never forms a valid Indian read,
# so a vote on it never settles; real Gujarat traffic does. It is replaced by
# a drawn GJ01AB1234 plate, which the production reader reads exactly.
PLATE_BOX = (301, 185, 392, 211)
OUT_DIR = REPO_ROOT / "evidence"
PUBLISH = "rtsp://dev-grid:dev-grid-local-only@127.0.0.1:8554/dev/{path}"
READ = "rtsp://127.0.0.1:8554/dev/{path}"
CROSSING_S = 12
"""Seconds for the vehicles to cross the frame: about 235 px between frames
analysed at 8 fps, the far end of real junction traffic. Faster than this
the tracker loses the vehicle between analysed frames."""
FPS = 25


@dataclass(slots=True)
class RunResult:
    tier: str
    cameras: int
    sampled_fps: float
    stride: int
    target_fps: float
    analysed_fps_median: float
    analysed_fps_min: float
    lag_s_max: float
    lag_s_end: float
    """Worst camera's median lag over the last third of the run: steady
    state, after the relay's connect-time replay has drained."""
    cameras_live: int
    worker_cpu_pct: float

    @property
    def keeps_up(self) -> bool:
        return (
            self.cameras_live == self.cameras
            and self.analysed_fps_min >= 0.8 * self.target_fps
            and self.lag_s_end < 5
        )


def make_vehicle_image() -> None:
    import cv2

    image = cv2.imread(str(SOURCE_IMAGE))
    if image is None:
        raise SystemExit(f"missing {SOURCE_IMAGE.relative_to(REPO_ROOT)}")
    x1, y1, x2, y2 = PLATE_BOX
    cv2.rectangle(image, (x1, y1), (x2, y2), (245, 245, 245), -1)
    cv2.rectangle(image, (x1, y1), (x2, y2), (20, 20, 20), 1)
    font, text, scale = cv2.FONT_HERSHEY_SIMPLEX, "GJ01AB1234", 2.0
    while cv2.getTextSize(text, font, scale, 1)[0][0] > (x2 - x1) * 0.9:
        scale -= 0.02
    (width, height), _ = cv2.getTextSize(text, font, scale, 1)
    origin = (x1 + (x2 - x1 - width) // 2, y1 + (y2 - y1 + height) // 2)
    cv2.putText(image, text, origin, font, scale, (10, 10, 10), 1, cv2.LINE_AA)
    cv2.imwrite(str(VEHICLE_IMAGE), image)


def make_clip() -> None:
    if CLIP.exists():
        return
    CLIP.parent.mkdir(parents=True, exist_ok=True)
    make_vehicle_image()
    travel = 1920 + 900
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x5a5a5a:s=1920x1080:r={FPS}:d={CROSSING_S}",
            "-loop",
            "1",
            "-i",
            str(VEHICLE_IMAGE),
            "-filter_complex",
            f"[1]scale=900:-2[car];[0][car]overlay=x='-900+t*{travel / CROSSING_S}':y=420:"
            "shortest=1,noise=alls=6:allf=t,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-g",
            str(FPS * 2),
            "-b:v",
            "4M",
            "-t",
            str(CROSSING_S),
            str(CLIP),
        ],
        check=True,
    )


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise SystemExit("ffmpeg not found on PATH (brew install ffmpeg)")
    return path


def start_publishers(paths: list[str]) -> list[subprocess.Popen[bytes]]:
    return [
        subprocess.Popen(
            [
                _ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-re",
                "-stream_loop",
                "-1",
                "-i",
                str(CLIP),
                "-c",
                "copy",
                "-f",
                "rtsp",
                "-rtsp_transport",
                "tcp",
                PUBLISH.format(path=path),
            ],
            stdin=subprocess.DEVNULL,
        )
        for path in paths
    ]


def process_tree_cpu(root_pid: int) -> float:
    """Summed %CPU of a process and its descendants (`uv run` spawns python)."""
    table = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,%cpu="], capture_output=True, text=True, check=True
    ).stdout
    children: dict[int, list[int]] = {}
    cpu: dict[int, float] = {}
    for line in table.splitlines():
        pid_s, ppid_s, pct_s = line.split()
        children.setdefault(int(ppid_s), []).append(int(pid_s))
        cpu[int(pid_s)] = float(pct_s)
    total, stack = 0.0, [root_pid]
    while stack:
        current = stack.pop()
        total += cpu.get(current, 0.0)
        stack.extend(children.get(current, []))
    return total


async def delete_load_cameras() -> None:
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import create_async_engine

    from core_api.db.base import _asyncpg_url
    from core_api.db.models import Camera
    from sentinel_core.config import get_settings

    # A fresh engine per call: each asyncio.run() is a new event loop, and
    # the API's cached engine is bound to the first one.
    engine = create_async_engine(_asyncpg_url(get_settings().app_database_url))
    try:
        async with engine.begin() as connection:
            await connection.execute(delete(Camera).where(Camera.camera_id.like("load-%")))
    finally:
        await engine.dispose()


def register(client: httpx.Client, ids: list[str], tier: str) -> None:
    for camera_id in ids:
        response = client.post(
            "/api/v1/cameras",
            json={
                "camera_id": camera_id,
                "name": f"Load test {camera_id}",
                "department_name": "Load test",
                "tier": tier,
                "profiles": [
                    {
                        "protocol": "rtsp",
                        "url": READ.format(path=camera_id),
                        "codec": "h264",
                        "width": 1920,
                        "height": 1080,
                        "declared_fps": FPS,
                    }
                ],
            },
        )
        response.raise_for_status()


def run_once(
    client: httpx.Client,
    *,
    tier: str,
    n: int,
    sampled_fps: float,
    duration_s: float,
    stride: int = 1,
) -> RunResult:
    ids = [f"load-{tier[0]}{n:02d}-{i:02d}" for i in range(1, n + 1)]
    asyncio.run(delete_load_cameras())
    publishers = start_publishers(ids)
    worker: subprocess.Popen[bytes] | None = None
    try:
        time.sleep(2)
        register(client, ids, tier)
        worker = subprocess.Popen(
            [
                "uv",
                "run",
                "--package",
                "edge-agent",
                "python",
                "-m",
                "edge_agent.worker",
                "--source",
                "registry",
                "--cameras",
                ",".join(ids),
                "--sampled-fps",
                str(sampled_fps),
                "--frame-stride",
                str(stride),
                "--resync-interval",
                "0",
            ],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        warmup = min(30.0, duration_s / 3)
        time.sleep(warmup)
        fps: dict[str, list[float]] = {camera_id: [] for camera_id in ids}
        lags: dict[str, list[float]] = {camera_id: [] for camera_id in ids}
        cpu: list[float] = []
        live: set[str] = set()
        deadline = time.monotonic() + duration_s - warmup
        while time.monotonic() < deadline:
            time.sleep(5)
            cpu.append(process_tree_cpu(worker.pid))
            for camera in client.get("/api/v1/cameras").json():
                if camera["camera_id"] not in fps:
                    continue
                if camera.get("analysed_fps") is not None:
                    fps[camera["camera_id"]].append(camera["analysed_fps"])
                if camera.get("analysis_lag_s") is not None:
                    lags[camera["camera_id"]].append(camera["analysis_lag_s"])
                if camera.get("status") == "live":
                    live.add(camera["camera_id"])
        per_camera = [statistics.median(v) if v else 0.0 for v in fps.values()]
        all_lags = [lag for series in lags.values() for lag in series]
        end_lags = [
            statistics.median(series[-max(1, len(series) // 3) :])
            for series in lags.values()
            if series
        ]
        target = FPS / stride if tier == "a_continuous" else sampled_fps
        return RunResult(
            tier=tier,
            cameras=n,
            sampled_fps=sampled_fps,
            stride=stride,
            target_fps=round(target, 1),
            analysed_fps_median=round(statistics.median(per_camera), 1),
            analysed_fps_min=round(min(per_camera), 1),
            lag_s_max=round(max(all_lags), 1) if all_lags else float("nan"),
            lag_s_end=round(max(end_lags), 1) if end_lags else float("nan"),
            cameras_live=len(live),
            worker_cpu_pct=round(statistics.median(cpu), 0) if cpu else 0.0,
        )
    finally:
        if worker is not None:
            os.killpg(worker.pid, signal.SIGTERM)
            try:
                worker.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(worker.pid, signal.SIGKILL)
        for publisher in publishers:
            publisher.terminate()
        for publisher in publishers:
            publisher.wait(timeout=10)
        asyncio.run(delete_load_cameras())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--tier", default="b_sampled", choices=["a_continuous", "b_sampled", "c_motion_gated"]
    )
    parser.add_argument("--cameras", type=int, nargs="+", default=[2, 4, 8])
    parser.add_argument("--sampled-fps", type=float, default=8.0)
    parser.add_argument("--stride", type=int, default=1, help="tier A: analyse every Nth frame")
    parser.add_argument("--duration", type=float, default=90.0, help="seconds per run")
    parser.add_argument(
        "--api", default=os.environ.get("SENTINEL_CORE_API_URL", "http://127.0.0.1:18000")
    )
    parser.add_argument("--email", default="admin@sentinel-platform.com")
    parser.add_argument("--password", default="sentinel-admin-2026")
    args = parser.parse_args()

    make_clip()
    with httpx.Client(base_url=args.api, timeout=15) as client:
        login = client.post(
            "/api/v1/auth/login", json={"email": args.email, "password": args.password}
        )
        if login.status_code != 200:
            raise SystemExit(f"login failed ({login.status_code}): run `make seed` first")
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        results = []
        for n in args.cameras:
            print(f"-- {args.tier}, {n} camera(s), {args.duration:.0f} s ...", flush=True)
            result = run_once(
                client,
                tier=args.tier,
                n=n,
                sampled_fps=args.sampled_fps,
                duration_s=args.duration,
                stride=args.stride,
            )
            results.append(result)
            verdict = "keeps up" if result.keeps_up else "FALLS BEHIND"
            print(
                f"   analysed fps median {result.analysed_fps_median} / min "
                f"{result.analysed_fps_min} (target {result.target_fps}), lag max "
                f"{result.lag_s_max} s / end {result.lag_s_end} s, "
                f"live {result.cameras_live}/{n}, worker CPU "
                f"{result.worker_cpu_pct:.0f}%  -> {verdict}",
                flush=True,
            )

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_DIR / f"tier-capacity-{args.tier}-{stamp}.csv"
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([*RunResult.__dataclass_fields__, "keeps_up", "cpu_cores", "host"])
        for r in results:
            writer.writerow(
                [
                    *(getattr(r, k) for k in RunResult.__dataclass_fields__),
                    r.keeps_up,
                    os.cpu_count(),
                    os.uname().machine,
                ]
            )
    print(f"\nwritten to {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
