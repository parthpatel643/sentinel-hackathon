#!/usr/bin/env python3
"""Build a blind-labelling holdout for reading cameras' burned-in clocks.

`scripts/eval_clock.py` scores a clock reader against `frame,ground_truth`
pairs, and the only honest ground truth is a person reading each overlay.
This script prepares that work without anchoring the labeller:

1. samples whole frames, with a fixed seed so the sample is reproducible:
   evenly spaced frames from every camera's recording in the government-grid
   mirror (data/gov-mirror/clips), plus detection snapshots the live pipeline
   saved (data/snapshots), split between ones the current reader verified
   and ones it did not, so both are represented;
2. writes each frame as the reader will receive it (full resolution);
3. tiles, per frame, the four frame edges where cameras print their clock
   into numbered contact sheets — *without* any OCR output;
4. writes `labels.csv` with an empty `ground_truth` column to fill in, as
   `YYYY-MM-DD HH:MM:SS` in the camera's own local time, or `UNREADABLE`
   where a person cannot read every digit either (or there is no clock).

Images stay under data/ (gitignored): the organisers' footage is
consume-only, so frames are never committed; labels and results are.

    uv run --package edge-agent python scripts/build_clock_holdout.py
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIRROR = REPO_ROOT / "data" / "gov-mirror"
DEFAULT_SNAPSHOTS = REPO_ROOT / "data" / "snapshots"
DEFAULT_OUT = REPO_ROOT / "data" / "clock-holdout"

# Edges of the frame where the fleet prints its clock: (y0, y1, x0, x1) as
# fractions, matching the corners the reader searches.
BANDS = {
    "top": (0.0, 0.10, 0.0, 1.0),
    "bottom": (0.90, 1.0, 0.0, 1.0),
}
SHEET_WIDTH = 1600


def snapshot_sample(per_bucket: int, rng: random.Random) -> list[tuple[str, str, bool]]:
    """(camera_id, snapshot ulid, verified) from the live database: the
    current reader's verified and unverified reads, per camera."""
    query = (
        "select camera_id, substring(snapshot_uri from 12), camera_time is not null "
        "from detections where snapshot_uri is not null"
    )
    out = subprocess.run(
        [
            "docker",
            "exec",
            "sentinel-postgres",
            "sh",
            "-c",
            f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "|" -c "{query}"',
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    buckets: dict[tuple[str, bool], list[str]] = {}
    for line in out.splitlines():
        camera, ulid, flag = line.split("|")
        buckets.setdefault((camera, flag == "t"), []).append(ulid)
    chosen: list[tuple[str, str, bool]] = []
    for (camera, verified), ulids in sorted(buckets.items()):
        for ulid in rng.sample(sorted(ulids), min(per_bucket, len(ulids))):
            chosen.append((camera, ulid, verified))
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-clip", type=int, default=4, help="frames per mirrored camera")
    parser.add_argument(
        "--per-bucket", type=int, default=10, help="snapshots per (camera, verified-or-not) bucket"
    )
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--mirror", type=Path, default=DEFAULT_MIRROR)
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    import cv2
    import numpy as np

    rng = random.Random(args.seed)
    frames_dir = args.out / "frames"
    sheets_dir = args.out / "sheets"
    frames_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    manifest = json.loads((args.mirror / "manifest.json").read_text())
    for clip in manifest:
        cap = cv2.VideoCapture(str(args.mirror / clip["clip"]))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            continue
        for k in range(args.per_clip):
            # Evenly spread, with jitter: sections of a stitched recording
            # differ (scene cuts, decoder damage), and so does the clock.
            position = int(total * (k + rng.uniform(0.2, 0.8)) / args.per_clip)
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(position, total - 1))
            ok, frame = cap.read()
            if not ok:
                continue
            name = f"{clip['camera_id']}-m{k}.png"
            cv2.imwrite(str(frames_dir / name), frame)
            rows.append(
                {
                    "frame": f"frames/{name}",
                    "camera_id": clip["camera_id"],
                    "source": "mirror",
                    "current_verified": "",
                }
            )
        cap.release()

    for camera, ulid, verified in snapshot_sample(args.per_bucket, rng):
        src = args.snapshots / f"{ulid}.jpg"
        if not src.exists():
            continue
        snapshot = cv2.imread(str(src))
        if snapshot is None:
            continue
        name = f"{camera}-s-{ulid}.png"
        cv2.imwrite(str(frames_dir / name), snapshot)
        rows.append(
            {
                "frame": f"frames/{name}",
                "camera_id": camera,
                "source": "snapshot",
                "current_verified": "yes" if verified else "no",
            }
        )

    # Labelling sheets: the edges only, numbered, no OCR output anywhere.
    rng.shuffle(rows)
    tiles: list[np.ndarray] = []
    for index, row in enumerate(rows, start=1):
        row["id"] = f"c{index:04d}"
        image = cv2.imread(str(args.out / row["frame"]))
        if image is None:
            continue
        height, width = image.shape[:2]
        strips = []
        for y0, y1, x0, x1 in BANDS.values():
            band = image[int(height * y0) : int(height * y1), int(width * x0) : int(width * x1)]
            band = cv2.resize(band, (SHEET_WIDTH, int(band.shape[0] * SHEET_WIDTH / band.shape[1])))
            strips.append(band)
        label = np.full((34, SHEET_WIDTH, 3), 255, np.uint8)
        cv2.putText(label, row["id"], (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        tiles.append(
            np.vstack([label, strips[0], np.full((6, SHEET_WIDTH, 3), 255, np.uint8), strips[1]])
        )
    per_sheet = 5
    for start in range(0, len(tiles), per_sheet):
        sheet = np.vstack(
            [
                np.vstack([t, np.full((14, SHEET_WIDTH, 3), 255, np.uint8)])
                for t in tiles[start : start + per_sheet]
            ]
        )
        cv2.imwrite(
            str(sheets_dir / f"sheet-{start // per_sheet + 1:03d}.jpg"),
            sheet,
            [cv2.IMWRITE_JPEG_QUALITY, 92],
        )

    with (args.out / "labels.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["id", "frame", "camera_id", "source", "current_verified", "ground_truth"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "ground_truth": ""})
    print(f"{len(rows)} frames, {len(tiles) // per_sheet + 1} sheets -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
