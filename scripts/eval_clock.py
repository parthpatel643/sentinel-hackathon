#!/usr/bin/env python3
"""Score camera-clock readers against the hand-labelled clock holdout.

Each frame in `labels.csv` (built by `scripts/build_clock_holdout.py`) is
read by every engine from scratch: no memory of earlier frames and no
cross-frame verification, so this measures what one frame gives an engine.
Production then requires a second reading to agree before a time is used
(`FrameClockReader.verified`), which turns some single-frame misreads into
"time unknown" rather than a wrong time; that is scored separately below.

Outcomes per labelled frame:
  exact    the engine's timestamp equals the label, to the second
  wrong    the engine produced a plausible timestamp that is not the label
           (the dangerous outcome: a confident wrong time)
  missed   the engine produced nothing

Frames labelled UNREADABLE are excluded from accuracy; an engine that still
produces a time on them is counted as `invented`.

    uv run --package edge-agent python scripts/eval_clock.py data/clock-holdout/labels.csv \\
        --engine production --engine production-tracked --out evidence/clock-holdout-results.csv

    git show 5ab1d95:services/edge_agent/src/edge_agent/analytics/frame_clock.py > /tmp/old.py
    CLOCK_TESSERACT_MODULE=/tmp/old.py uv run --package edge-agent --with pytesseract \\
        python scripts/eval_clock.py data/clock-holdout/labels.csv --engine tesseract
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

Read = Callable[[np.ndarray], datetime | None]

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_engine(name: str) -> Read:
    """Returns `read(frame) -> datetime | None` for a named engine."""
    from edge_agent.analytics import frame_clock

    if name == "tesseract":
        # The reader this replaced, kept for comparison: pass its source with
        # CLOCK_TESSERACT_MODULE=path/to/old/frame_clock.py and --with pytesseract.
        spec = importlib.util.spec_from_file_location(
            "tesseract_frame_clock", os.environ["CLOCK_TESSERACT_MODULE"]
        )
        assert spec is not None and spec.loader is not None
        old: Any = importlib.util.module_from_spec(spec)
        sys.modules["tesseract_frame_clock"] = old
        spec.loader.exec_module(old)

        def read_tesseract(frame: np.ndarray) -> datetime | None:
            reader = old.FrameClockReader()
            text = reader._ocr(frame)
            if text is None:
                return None
            parsed = old.parse_overlay_timestamp(text)
            ok = parsed is not None and reader._is_plausible(parsed)
            return parsed if ok else None

        return read_tesseract
    if name == "production":
        # The reader as the worker runs it, on a camera it has never read:
        # detection over the frame's edges, then recognition.
        def read_first(frame: np.ndarray) -> datetime | None:
            reader = frame_clock.FrameClockReader()
            return reader.read_now(frame, pts_ms=0.0)

        return read_first
    if name == "production-tracked":
        # The steady state: the camera's clock box is already known (found on
        # this frame), and only that box is recognised.
        def read_tracked(frame: np.ndarray) -> datetime | None:
            reader = frame_clock.FrameClockReader(full_scan_interval_s=1e9)
            if reader.read_now(frame, pts_ms=0.0) is None:
                return None
            return reader.read_now(frame, pts_ms=5000.0)

        return read_tracked
    raise SystemExit(f"unknown engine {name!r}")


def truth_utc(label: str) -> datetime | None:
    from edge_agent.analytics.frame_clock import IST

    if label == "UNREADABLE":
        return None
    return datetime.strptime(label, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST).astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("labels", type=Path)
    parser.add_argument("--engine", action="append", default=[])
    parser.add_argument("--out", type=Path, help="per-frame results CSV")
    args = parser.parse_args()
    engines = args.engine or ["production"]

    import cv2

    root = args.labels.parent
    rows = [r for r in csv.DictReader(args.labels.open()) if r["ground_truth"].strip()]
    if not rows:
        raise SystemExit("no labelled rows")
    results: list[dict[str, str]] = []
    tallies: dict[str, Counter[str]] = {}
    timings: dict[str, list[float]] = {}
    for name in engines:
        read = load_engine(name)
        tally: Counter[str] = Counter()
        latencies: list[float] = []
        for row in rows:
            frame = cv2.imread(str(root / row["frame"]))
            if frame is None:
                raise SystemExit(f"cannot read {row['frame']}")
            started = time.perf_counter()
            got = read(frame)
            latencies.append((time.perf_counter() - started) * 1000)
            truth = truth_utc(row["ground_truth"].strip())
            if truth is None:
                outcome = "invented" if got is not None else "abstained"
            elif got is None:
                outcome = "missed"
            else:
                outcome = "exact" if got == truth else "wrong"
            tally[outcome] += 1
            results.append(
                {
                    "engine": name,
                    "id": row["id"],
                    "camera_id": row["camera_id"],
                    "source": row["source"],
                    "truth": row["ground_truth"],
                    "read": got.isoformat() if got else "",
                    "outcome": outcome,
                }
            )
        tallies[name], timings[name] = tally, latencies

    readable = sum(1 for r in rows if r["ground_truth"].strip() != "UNREADABLE")
    print(f"{len(rows)} labelled frames, {readable} with a readable clock\n")
    print(
        f"{'engine':<12}{'exact':>14}{'wrong':>12}{'missed':>12}"
        f"{'invented':>10}{'median ms':>11}{'p95 ms':>9}"
    )

    def pct(n: int) -> str:
        return f"{n} ({100 * n / readable:.1f}%)"

    for name, t in tallies.items():
        lat = sorted(timings[name])
        p95 = lat[int(0.95 * (len(lat) - 1))]
        print(
            f"{name:<12}{pct(t['exact']):>14}{pct(t['wrong']):>12}{pct(t['missed']):>12}"
            f"{t['invented']:>10}{statistics.median(lat):>11.0f}{p95:>9.0f}"
        )
    if args.out:
        with args.out.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(results[0]))
            writer.writeheader()
            writer.writerows(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
