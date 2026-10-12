#!/usr/bin/env python3
"""Replay recorded camera streams through a clock reader the way the worker
runs it, and measure what reaches evidence.

`scripts/eval_clock.py` scores single frames against hand labels. This
script measures the production behaviour instead: frames are fed in stream
order at the analysed rate, the reader reads at most once per stream second,
and a reading counts only once `FrameClockReader.verified()` confirms it
against another reading of the same camera's clock.

Per camera it reports:
  coverage     share of stream seconds whose frame has a verified time
  outliers     verified times inconsistent with both neighbouring verified
               times (a clock may stall, but never runs backwards or faster
               than the footage, beyond --tolerance seconds): a verified
               time that is wrong
  ms/read      mean reader time per stream second

    uv run --package edge-agent python scripts/replay_clock.py --seconds 120
    uv run --package edge-agent --with pytesseract python scripts/replay_clock.py \\
        --reader-module /path/to/old_frame_clock.py      # compare another reader
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIRROR = REPO_ROOT / "data" / "gov-mirror"
VERIFY_AFTER_MS = 3000.0


def load_reader_class(path: Path | None) -> Callable[..., Any]:
    if path is None:
        from edge_agent.analytics.frame_clock import FrameClockReader

        return FrameClockReader
    spec = importlib.util.spec_from_file_location("alt_frame_clock", path)
    assert spec is not None and spec.loader is not None
    module: Any = importlib.util.module_from_spec(spec)
    sys.modules["alt_frame_clock"] = module
    spec.loader.exec_module(module)
    reader: Callable[..., Any] = module.FrameClockReader
    return reader


def replay(
    clip: Path,
    reader_cls: Callable[..., Any],
    seconds: float,
    start_fraction: float,
    tolerance: float,
    dump: Path | None = None,
) -> dict[str, float]:
    import cv2

    cap = cv2.VideoCapture(str(clip))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * start_fraction))
    reader = reader_cls()
    read_frames: list[float] = []
    pending: list[float] = []
    verified: list[tuple[float, datetime]] = []
    frames_by_pts: dict[float, Any] = {}
    spent = 0.0
    first_ms: float | None = None
    last_ms = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # The frame's own presentation time, as the worker gets it from the
        # stream: these recordings are variable-rate, so index / fps drifts.
        pts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        if first_ms is None:
            first_ms = pts_ms
        if pts_ms - first_ms > seconds * 1000:
            break
        last_ms = pts_ms
        before = time.perf_counter()
        value = reader.observe(frame, pts_ms=pts_ms)
        spent += time.perf_counter() - before
        if value is not None:
            read_frames.append(pts_ms)
            pending.append(pts_ms)
            if dump is not None:
                frames_by_pts[pts_ms] = frame
        # As in production, a reading is checked a few seconds after it is
        # taken (when its sighting is emitted), not after the reader's
        # bounded history has moved on.
        while pending and pts_ms - pending[0] >= VERIFY_AFTER_MS:
            checked = pending.pop(0)
            if (value := reader.verified(checked)) is not None:
                verified.append((checked, value))
    cap.release()
    stream_seconds = max(1, int((last_ms - (first_ms or 0.0)) / 1000))
    for checked in pending:
        if (value := reader.verified(checked)) is not None:
            verified.append((checked, value))
    # A camera clock can stall (a held frame, a stalled recorder) but cannot
    # run backwards or faster than the footage. Between consecutive verified
    # readings, anything else is a misread; a reading that breaks the rule
    # with both its neighbours is the wrong one. A stitched recording's jumps
    # break it too, so a pair more than `section_gap` apart in the clock is
    # treated as a cut, not compared.
    verified.sort(key=lambda item: item[0])

    def consistent(a: tuple[float, datetime], b: tuple[float, datetime]) -> bool:
        footage = (b[0] - a[0]) / 1000.0
        clock = (b[1] - a[1]).total_seconds()
        if abs(clock - footage) > 120:
            return True
        return bool(-tolerance <= clock <= footage + tolerance)

    outliers = 0
    for i, item in enumerate(verified):
        neighbours = [verified[j] for j in (i - 1, i + 1) if 0 <= j < len(verified)]
        if len(neighbours) == 2 and not any(
            consistent(*sorted((item, n), key=lambda x: x[0])) for n in neighbours
        ):
            outliers += 1
            if dump is not None:
                stem = f"{clip.stem}-{int(item[0])}"
                cv2.imwrite(str(dump / f"{stem}.jpg"), frames_by_pts[item[0]])
                with (dump / "outliers.csv").open("a") as fh:
                    prev, nxt = neighbours
                    fh.write(
                        f"{stem},{item[1].isoformat()},{prev[1].isoformat()},"
                        f"{(item[0] - prev[0]) / 1000:.2f},"
                        f"{nxt[1].isoformat()},{(nxt[0] - item[0]) / 1000:.2f}\n"
                    )
    return {
        "stream_s": stream_seconds,
        "verified": len(verified),
        # A window's partial last second can hold a verified reading too.
        "coverage": min(1.0, len({int(pts // 1000) for pts, _ in verified}) / stream_seconds),
        "outliers": outliers,
        "ms_per_s": 1000 * spent / stream_seconds,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mirror", type=Path, default=DEFAULT_MIRROR)
    parser.add_argument("--seconds", type=float, default=120.0, help="stream seconds per window")
    parser.add_argument("--windows", type=int, default=2, help="windows per camera")
    parser.add_argument("--tolerance", type=float, default=3.0)
    parser.add_argument("--reader-module", type=Path, help="alternative frame_clock.py to compare")
    parser.add_argument("--cameras", help="comma-separated ids (default: all)")
    parser.add_argument("--out", type=Path, help="per-camera results JSON")
    parser.add_argument("--dump", type=Path, help="write each outlier's frame and neighbours here")
    parser.add_argument(
        "--agreement-tolerance", type=float, help="override the reader's agreement_tolerance_s"
    )
    args = parser.parse_args()

    reader_cls = load_reader_class(args.reader_module)
    if args.agreement_tolerance is not None:
        import functools

        reader_cls = functools.partial(reader_cls, agreement_tolerance_s=args.agreement_tolerance)
    if args.dump:
        args.dump.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.mirror / "manifest.json").read_text())
    wanted = set(args.cameras.split(",")) if args.cameras else None
    results = {}
    for clip in manifest:
        if wanted and clip["camera_id"] not in wanted:
            continue
        windows = [
            replay(
                args.mirror / clip["clip"],
                reader_cls,
                args.seconds,
                (k + 0.5) / (args.windows + 1),
                args.tolerance,
                args.dump,
            )
            for k in range(args.windows)
        ]
        stream = sum(w["stream_s"] for w in windows)
        results[clip["camera_id"]] = {
            "stream_s": stream,
            "coverage": sum(w["coverage"] * w["stream_s"] for w in windows) / stream,
            "verified": sum(w["verified"] for w in windows),
            "outliers": sum(w["outliers"] for w in windows),
            "ms_per_s": sum(w["ms_per_s"] * w["stream_s"] for w in windows) / stream,
        }
        r = results[clip["camera_id"]]
        print(
            f"{clip['camera_id']}  coverage {100 * r['coverage']:5.1f}%  "
            f"verified {r['verified']:4d}  "
            f"outliers {r['outliers']:3d}  {r['ms_per_s']:6.0f} ms/s",
            flush=True,
        )
    stream = sum(r["stream_s"] for r in results.values())
    print(
        f"\nall    coverage "
        f"{100 * sum(r['coverage'] * r['stream_s'] for r in results.values()) / stream:5.1f}%  "
        f"verified {sum(r['verified'] for r in results.values())}  "
        f"outliers {sum(r['outliers'] for r in results.values())}  "
        f"{sum(r['ms_per_s'] * r['stream_s'] for r in results.values()) / stream:.0f} ms/s"
    )
    if args.out:
        args.out.write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
