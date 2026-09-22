#!/usr/bin/env python3
"""M1 capacity benchmark — how many concurrent streams can this machine decode?

This is the highest-risk unknown in the whole build (see docs/05-DELIVERY-PLAN
milestone M1): if a single machine cannot sustain the ~50-camera government
grid at a workable analytics rate, the tiering strategy in the HLD has to be
tuned *before* any feature work, not discovered on submission day.

Method: open N concurrent RTSP connections against the local synthetic grid
(round-robining across its 8 published cameras — the organisers' own gateway
gives each client its own stream copy, so re-using the same source cameras is
a faithful proxy for N independent connections). Each stream is read as fast
as it will actually deliver for a fixed measurement window, and the result is
scored against THAT STREAM'S OWN declared rate (achieved / declared) — a
"keep-up ratio". A global mean across streams hides exactly the failure mode
that matters here: some streams stalling hard while others look fine drags
the mean up and hides the problem, so the ceiling is defined by the number of
INDIVIDUALLY degraded streams, not the average.

CAVEAT — read before quoting this number to anyone: on this machine, the
synthetic grid's 8 publisher processes AND the MediaMTX relay ALSO run on the
same CPU as the consumers being measured, competing for the same cores. A real
deployment's edge agent does not share a machine with the cameras it decodes.
This is therefore a conservative (pessimistic), not optimistic, estimate of
true decode capacity — which is the safer direction to be wrong in for a live
demo, but it should not be quoted as "the M4's absolute ceiling" without that
caveat attached.

Usage:
    uv run python scripts/synthetic_grid.py all      # if not already running
    uv run python scripts/bench_capacity.py
    uv run python scripts/bench_capacity.py --max-cameras 60 --step 4
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import platform
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "sentinel_core" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "edge_agent" / "src"))

EVIDENCE_DIR = REPO_ROOT / "evidence"

# Matches scripts/synthetic_grid.py's CAMERAS list.
GRID_CAMERA_IDS = [f"dev-cam-{i:02d}" for i in range(1, 9)]
RELAY_RTSP_URL = "rtsp://127.0.0.1:8554/dev"

# A stream keeping up at 70% of its own declared rate is "healthy" — some
# margin below 100% is expected and fine (GOP-replay bursts, brief gaps);
# well below that means decode genuinely cannot keep pace.
HEALTHY_KEEP_UP_RATIO = 0.7


@dataclass(slots=True)
class WorkerResult:
    camera_id: str
    opened: bool
    frames: int
    elapsed_s: float
    declared_fps: float | None

    @property
    def achieved_fps(self) -> float:
        return self.frames / self.elapsed_s if self.elapsed_s > 0 else 0.0

    @property
    def keep_up_ratio(self) -> float | None:
        """achieved / declared for THIS stream. None if we never learned the
        declared rate (e.g. the connection died before FPS metadata arrived)."""
        if not self.declared_fps:
            return None
        return self.achieved_fps / self.declared_fps


@dataclass(slots=True)
class StepResult:
    n_cameras: int
    opened: int
    failed: int
    degraded: int
    """Streams whose keep-up ratio fell below HEALTHY_KEEP_UP_RATIO."""
    mean_keep_up_ratio: float
    min_keep_up_ratio: float
    wall_seconds: float

    @property
    def degraded_fraction(self) -> float:
        return self.degraded / self.opened if self.opened else 1.0


async def _run_one_camera(camera_id: str, url: str, duration_s: float) -> WorkerResult:
    from edge_agent.pipeline.capture import CaptureConfig, RtspCapture

    capture = RtspCapture(config=CaptureConfig(camera_id=camera_id, url=url))
    opened = await asyncio.to_thread(capture.open)
    if not opened:
        return WorkerResult(camera_id, False, 0, 0.0, None)

    start = time.monotonic()
    frames = 0
    while time.monotonic() - start < duration_s:
        frame = await asyncio.to_thread(capture.read)
        if frame is not None:
            frames += 1
    elapsed = time.monotonic() - start
    result = WorkerResult(camera_id, True, frames, elapsed, capture.declared_fps)
    capture.close()
    return result


async def _run_step(n_cameras: int, duration_s: float, source_ids: list[str]) -> StepResult:
    tasks = []
    for i in range(n_cameras):
        source_id = source_ids[i % len(source_ids)]
        url = f"{RELAY_RTSP_URL}/{source_id}"
        tasks.append(_run_one_camera(f"bench-{i:03d}-{source_id}", url, duration_s))

    wall_start = time.monotonic()
    results = await asyncio.gather(*tasks)
    wall_seconds = time.monotonic() - wall_start

    opened_results = [r for r in results if r.opened]
    failed = len(results) - len(opened_results)
    ratios = [r.keep_up_ratio for r in opened_results if r.keep_up_ratio is not None]
    degraded = sum(1 for r in ratios if r < HEALTHY_KEEP_UP_RATIO) + (
        len(opened_results) - len(ratios)
    )

    return StepResult(
        n_cameras=n_cameras,
        opened=len(opened_results),
        failed=failed,
        degraded=degraded,
        mean_keep_up_ratio=statistics.mean(ratios) if ratios else 0.0,
        min_keep_up_ratio=min(ratios) if ratios else 0.0,
        wall_seconds=wall_seconds,
    )


def _write_csv(steps: list[StepResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "n_cameras",
                "opened",
                "failed",
                "degraded",
                "degraded_fraction",
                "mean_keep_up_ratio",
                "min_keep_up_ratio",
                "wall_seconds",
            ]
        )
        for s in steps:
            writer.writerow(
                [
                    s.n_cameras,
                    s.opened,
                    s.failed,
                    s.degraded,
                    f"{s.degraded_fraction:.3f}",
                    f"{s.mean_keep_up_ratio:.3f}",
                    f"{s.min_keep_up_ratio:.3f}",
                    f"{s.wall_seconds:.1f}",
                ]
            )


async def main(args: argparse.Namespace) -> None:
    # asyncio.to_thread always uses the loop's default executor. Left at its
    # default size (min(32, cpu_count+4)), it would silently cap concurrency
    # far below what we're trying to measure — so it must be sized to at
    # least max_cameras before anything runs.
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=args.max_cameras + 8))

    source_ids = [s.strip() for s in args.sources.split(",") if s.strip()]
    steps: list[StepResult] = []
    print(f"sources: {source_ids}")
    print(f"{'n_cams':>7} {'opened':>7} {'degraded':>9} {'mean_ratio':>11} {'min_ratio':>10}")
    for n in range(args.min_cameras, args.max_cameras + 1, args.step):
        step = await _run_step(n, args.duration, source_ids)
        steps.append(step)
        print(
            f"{n:>7} {step.opened:>7} {step.degraded:>9} "
            f"{step.mean_keep_up_ratio:>11.1%} {step.min_keep_up_ratio:>10.1%}"
        )
        if step.degraded_fraction > args.degradation_fraction:
            print(
                f"\n>{args.degradation_fraction:.0%} of streams degraded at n={n} — stopping ramp"
            )
            break

    host = platform.node().replace(" ", "-") or "unknown-host"
    chip = platform.processor() or platform.machine()
    date = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_path = EVIDENCE_DIR / f"capacity-{host}-{date}.csv"
    _write_csv(steps, out_path)

    # Ceiling: the largest N where no meaningful fraction of streams degraded.
    ceiling = next(
        (s.n_cameras for s in reversed(steps) if s.degraded_fraction <= args.degradation_fraction),
        0,
    )
    print(f"\nmachine: {host} ({chip})")
    print(f"capacity curve written to {out_path}")
    print(
        f"capacity ceiling (<={args.degradation_fraction:.0%} of streams degraded): "
        f"{ceiling} concurrent streams"
    )
    print(
        "\nCAVEAT: the synthetic grid's own publishers and the relay share this CPU "
        "with the consumers being measured — this is a conservative estimate, not the "
        "true decode ceiling. See the module docstring. Re-run on the M4 and record both."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--min-cameras", type=int, default=4)
    parser.add_argument("--max-cameras", type=int, default=48)
    parser.add_argument("--step", type=int, default=4)
    parser.add_argument(
        "--duration", type=float, default=8.0, help="measurement window per step, seconds"
    )
    parser.add_argument(
        "--degradation-fraction",
        type=float,
        default=0.1,
        help="stop ramping once more than this fraction of streams are degraded",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(GRID_CAMERA_IDS),
        help="comma-separated dev/* camera ids to round-robin against (fewer sources "
        "means fewer local synthetic-grid publisher processes competing for CPU)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
