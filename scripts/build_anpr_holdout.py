#!/usr/bin/env python3
"""Build a blind-labelling holdout for ANPR accuracy from saved snapshots.

`scripts/eval_anpr.py` needs `image_path,ground_truth_plate` pairs, and the
only honest ground truth is a human reading each plate. This script prepares
that work without biasing it:

1. samples snapshots the pipeline already saved (real camera frames, faces
   blurred), with a fixed seed so the sample is reproducible;
2. finds plates with the production plate detector and keeps those large
   enough for a person to read;
3. writes, per plate, a context crop (what `eval_anpr.py` will feed the
   reader, like the vehicle crop the live pipeline uses) and a zoomed view;
4. tiles the zoomed views into numbered contact sheets — *without* the
   model's read, so the labeller cannot be anchored by it;
5. writes `labels.csv` with an empty `ground_truth_plate` column to fill in
   (`UNREADABLE` where a person cannot read the plate either).

Images stay under data/ (gitignored): the organisers' footage is
consume-only, so frames and crops are never committed; labels and results
are, as evidence/m14-detections.csv already is.

    uv run --package edge-agent python scripts/build_anpr_holdout.py --plates 150
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOTS = REPO_ROOT / "data" / "snapshots"
DEFAULT_OUT = REPO_ROOT / "data" / "anpr-holdout"

MIN_PLATE_HEIGHT_PX = 14
SHEET_COLUMNS, SHEET_ROWS = 4, 5
ZOOM_WIDTH = 300


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plates", type=int, default=150, help="plates to collect")
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--max-per-frame", type=int, default=2, help="plates kept from any one frame"
    )
    args = parser.parse_args()

    import cv2
    from PIL import Image, ImageDraw

    from edge_agent.analytics.plate_reader import FastAlprPlateReader

    frames = sorted(args.snapshots.glob("*.jpg"))
    if not frames:
        print(f"no snapshots under {args.snapshots}", file=sys.stderr)
        return 1
    random.Random(args.seed).shuffle(frames)
    crops_dir, zoom_dir, sheets_dir = (args.out / d for d in ("crops", "zoom", "sheets"))
    for directory in (crops_dir, zoom_dir, sheets_dir):
        directory.mkdir(parents=True, exist_ok=True)

    reader = FastAlprPlateReader()
    rows: list[dict[str, str]] = []
    scanned = 0
    for frame_path in frames:
        if len(rows) >= args.plates:
            break
        image = cv2.imread(str(frame_path))
        scanned += 1
        if image is None:
            continue
        height, width = image.shape[:2]
        kept = 0
        for candidate in sorted(reader.read(image), key=lambda c: -c.mean_confidence):
            x1, y1, x2, y2 = (int(v) for v in candidate.bbox_xyxy)
            plate_w, plate_h = x2 - x1, y2 - y1
            if plate_h < MIN_PLATE_HEIGHT_PX or kept >= args.max_per_frame:
                continue
            crop_id = f"p{len(rows) + 1:04d}"
            # Context crop: generous, like the vehicle ROI the pipeline reads.
            cx1, cy1 = max(0, x1 - plate_w * 2), max(0, y1 - plate_h * 4)
            cx2, cy2 = min(width, x2 + plate_w * 2), min(height, y2 + plate_h * 4)
            crop_path = crops_dir / f"{crop_id}.jpg"
            cv2.imwrite(str(crop_path), image[cy1:cy2, cx1:cx2])
            # Zoomed view for the human: just the plate, enlarged.
            mx, my = int(plate_w * 0.15), int(plate_h * 0.25)
            plate = image[max(0, y1 - my) : y2 + my, max(0, x1 - mx) : x2 + mx]
            scale = ZOOM_WIDTH / max(1, plate.shape[1])
            zoom = cv2.resize(plate, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(str(zoom_dir / f"{crop_id}.png"), zoom)
            rows.append(
                {
                    "crop_id": crop_id,
                    "snapshot": frame_path.name,
                    "plate_height_px": str(plate_h),
                    "image_path": str(crop_path.relative_to(REPO_ROOT)),
                    "ground_truth_plate": "",
                }
            )
            kept += 1

    labels_path = args.out / "labels.csv"
    with labels_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    per_sheet = SHEET_COLUMNS * SHEET_ROWS
    cell_w, cell_h = ZOOM_WIDTH + 20, 150
    for start in range(0, len(rows), per_sheet):
        sheet = Image.new("RGB", (SHEET_COLUMNS * cell_w, SHEET_ROWS * cell_h), "white")
        draw = ImageDraw.Draw(sheet)
        for slot, row in enumerate(rows[start : start + per_sheet]):
            tile = Image.open(zoom_dir / f"{row['crop_id']}.png").convert("RGB")
            tile.thumbnail((ZOOM_WIDTH, cell_h - 28))
            x, y = (slot % SHEET_COLUMNS) * cell_w + 10, (slot // SHEET_COLUMNS) * cell_h
            draw.text((x, y + 4), row["crop_id"], fill="black")
            sheet.paste(tile, (x, y + 22))
        sheet.save(sheets_dir / f"sheet-{start // per_sheet + 1:02d}.jpg", quality=92)

    print(f"scanned {scanned} frames, kept {len(rows)} plates")
    print(f"label them in {labels_path} using the sheets in {sheets_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
