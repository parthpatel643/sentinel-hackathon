#!/usr/bin/env python3
"""Survey every camera briefly, then report which ones are worth watching.

The government grid has 30 cameras and this machine cannot analyse them all:
`evidence/M1-CAPACITY-FINDINGS.md` measured decode alone degrading at six
concurrent streams, and a 30-camera run drove load average past 49 and
tripped the grid's own viewing-time quota. So the useful question is not
"can we watch everything" but "which few are worth watching".

This answers it by measurement rather than guesswork: each camera gets a
short turn on the analytics pipeline, in small batches that stay inside both
the hardware budget and the grid's "pace your load" guidance, and the ones
that actually produce plate reads are reported. A camera pointed at an empty
service road ranks below one over a junction, and you find that out in
minutes instead of discovering it mid-demo.

Usage:
    uv run --package edge-agent python scripts/survey_cameras.py
    uv run --package edge-agent python scripts/survey_cameras.py \
        --batch 4 --dwell 90 --top 4
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = REPO_ROOT / "var" / "survey" / "camera-survey.json"

CORE_API_URL = os.environ.get("SENTINEL_CORE_API_URL", "http://localhost:18000")
ADMIN_EMAIL = os.environ.get("SENTINEL_ADMIN_EMAIL", "admin@sentinel-platform.com")
ADMIN_PASSWORD = os.environ.get("SENTINEL_ADMIN_PASSWORD", "sentinel-admin-2026")


@dataclass
class CameraResult:
    camera_id: str
    name: str
    detections: int
    distinct_plates: int
    reached: bool

    @property
    def score(self) -> tuple[int, int]:
        # Distinct plates first: fifty reads of one parked lorry is a worse
        # camera than five reads of five moving vehicles.
        return (self.distinct_plates, self.detections)


def _login() -> str:
    response = httpx.post(
        f"{CORE_API_URL}/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15.0,
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _cameras(token: str) -> list[dict[str, Any]]:
    response = httpx.get(f"{CORE_API_URL}/api/v1/cameras", headers=_headers(token), timeout=30.0)
    response.raise_for_status()
    cameras: list[dict[str, Any]] = response.json()
    return cameras


# The detections endpoint caps limit at 1000.
DETECTIONS_PAGE = 1000


def _detections(token: str, limit: int = DETECTIONS_PAGE) -> list[dict[str, Any]]:
    response = httpx.get(
        f"{CORE_API_URL}/api/v1/detections",
        params={"limit": limit},
        headers=_headers(token),
        timeout=60.0,
    )
    response.raise_for_status()
    payload = response.json()
    raw = payload.get("items", payload) if isinstance(payload, dict) else payload
    items: list[dict[str, Any]] = raw
    return items


def _run_batch(camera_ids: list[str], dwell_s: float, source: str) -> None:
    """Give one batch of cameras a turn on the pipeline.

    The worker is a long-running process by design, so a turn is "start it,
    let it settle and read, stop it". Terminated politely first so its
    captures close and the grid sees the connections go away — the guide asks
    for exactly that, and a survey that leaked a connection per batch would
    burn the quota it exists to protect.
    """
    command = [
        "uv", "run", "--package", "edge-agent", "python", "-m", "edge_agent.worker",
        "--source", source, "--cameras", ",".join(camera_ids),
    ]  # fmt: skip
    process = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )
    try:
        time.sleep(dwell_s)
    finally:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=20)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="gov", choices=["gov", "synthetic"])
    parser.add_argument(
        "--batch",
        type=int,
        default=4,
        help="cameras analysed at once. Kept small deliberately — six concurrent "
        "streams is where this hardware was measured to start degrading.",
    )
    parser.add_argument("--dwell", type=float, default=90.0, help="seconds per batch")
    parser.add_argument("--top", type=int, default=4, help="how many cameras to recommend")
    args = parser.parse_args()

    try:
        token = _login()
    except httpx.HTTPError as exc:
        print(f"could not log in to {CORE_API_URL}: {exc}", file=sys.stderr)
        return 2

    cameras = _cameras(token)
    if not cameras:
        print("no cameras registered — run POST /api/v1/cameras/discover first", file=sys.stderr)
        return 2

    # Count only what this survey produces, without deleting anyone's data.
    seen_before = {d["event_id"] for d in _detections(token)}
    names = {c["camera_id"]: c.get("display_name") or c["name"] for c in cameras}
    ids = [c["camera_id"] for c in cameras]

    batches = [ids[i : i + args.batch] for i in range(0, len(ids), args.batch)]
    total_s = len(batches) * args.dwell
    print(
        f"surveying {len(ids)} cameras in {len(batches)} batches of {args.batch}, "
        f"{args.dwell:.0f}s each (~{total_s / 60:.0f} min)\n"
    )

    for index, batch in enumerate(batches, start=1):
        print(f"[{index}/{len(batches)}] {', '.join(batch)}", flush=True)
        _run_batch(batch, args.dwell, args.source)

    new = [d for d in _detections(token) if d["event_id"] not in seen_before]
    per_camera = Counter(d["camera_id"] for d in new)
    plates: dict[str, set[str]] = {}
    for detection in new:
        plates.setdefault(detection["camera_id"], set()).add(detection["plate_normalised"])

    results = [
        CameraResult(
            camera_id=camera_id,
            name=names.get(camera_id, camera_id),
            detections=per_camera.get(camera_id, 0),
            distinct_plates=len(plates.get(camera_id, set())),
            reached=camera_id in per_camera,
        )
        for camera_id in ids
    ]
    results.sort(key=lambda r: r.score, reverse=True)

    print(f"\n{'camera':10} {'plates':>7} {'reads':>7}  name")
    print("-" * 68)
    for result in results:
        if result.detections == 0:
            continue
        print(
            f"{result.camera_id:10} {result.distinct_plates:>7} {result.detections:>7}  "
            f"{result.name[:38]}"
        )

    productive = [r for r in results if r.detections > 0]
    silent = len(results) - len(productive)
    print(f"\n{len(productive)} camera(s) produced reads, {silent} produced none in this window.")
    if not productive:
        print(
            "Nothing to recommend. A short window over quiet roads can legitimately "
            "produce nothing — re-run with a longer --dwell before concluding the "
            "cameras are unusable.",
            file=sys.stderr,
        )
        return 1

    top = productive[: args.top]
    chosen = [r.camera_id for r in top]
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(
            {
                "surveyed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "dwell_s": args.dwell,
                "batch": args.batch,
                "recommended": chosen,
                "results": [
                    {
                        "camera_id": r.camera_id,
                        "name": r.name,
                        "detections": r.detections,
                        "distinct_plates": r.distinct_plates,
                    }
                    for r in results
                ],
            },
            indent=2,
        )
        + "\n"
    )

    print(f"\nrecommended ({len(chosen)}): {', '.join(chosen)}")
    print(f"written to {RESULT_PATH.relative_to(REPO_ROOT)}\n")
    print("run them with:")
    print(
        "  uv run --package edge-agent python -m edge_agent.worker "
        f"--source {args.source} --cameras {','.join(chosen)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
