#!/usr/bin/env python3
"""ANPR accuracy evaluation against a labelled holdout.

Per docs/02-ANPR-PIPELINE.md section 7: no public benchmark with real Indian
plate data exists, so a holdout you build yourself from your own cameras is
the only way to state an accuracy number honestly. This script computes that
number once you have one; it does not fabricate one.

Expected input: a CSV with columns `image_path,ground_truth_plate`, where
each image is a single-vehicle or plate-region crop. Build this from
snapshots the pipeline already saves (see docs/01-ARCHITECTURE.md section
6.5, Evidence service) — every detection keeps a snapshot, so a few hours of
running the grid produces plenty of raw material; hand-label a stratified
sample (day/night, angle, distance, motion blur) as the frozen holdout.

Usage:
    uv run python scripts/eval_anpr.py holdout.csv
"""

from __future__ import annotations

import csv
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "sentinel_core" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "edge_agent" / "src"))

EVIDENCE_DIR = REPO_ROOT / "evidence"


@dataclass(slots=True)
class EvalRow:
    image_path: str
    ground_truth: str
    predicted: str | None
    plate_confidence: float
    latency_ms: float

    @property
    def exact_match(self) -> bool:
        return self.predicted == self.ground_truth

    @property
    def char_accuracy(self) -> float:
        """Position-wise match rate against the ground truth length. A
        length mismatch counts every extra/missing character as wrong."""
        if self.predicted is None:
            return 0.0
        length = max(len(self.ground_truth), len(self.predicted))
        if length == 0:
            return 1.0
        matches = sum(
            1
            for i in range(min(len(self.ground_truth), len(self.predicted)))
            if self.ground_truth[i] == self.predicted[i]
        )
        return matches / length


def _read_holdout(path: Path) -> list[tuple[str, str]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"image_path", "ground_truth_plate"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            print(f"CSV must have columns: {sorted(required)}", file=sys.stderr)
            raise SystemExit(1)
        return [(row["image_path"], row["ground_truth_plate"].strip().upper()) for row in reader]


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(1)

    holdout_path = Path(sys.argv[1])
    if not holdout_path.exists():
        print(f"no such file: {holdout_path}", file=sys.stderr)
        raise SystemExit(1)

    import cv2

    from edge_agent.analytics.plate_reader import FastAlprPlateReader

    entries = _read_holdout(holdout_path)
    if not entries:
        print("holdout file is empty", file=sys.stderr)
        raise SystemExit(1)

    print(f"loading OCR model, evaluating {len(entries)} entries ...")
    reader = FastAlprPlateReader()

    rows: list[EvalRow] = []
    for image_path, ground_truth in entries:
        image = cv2.imread(image_path)
        if image is None:
            print(f"  skipping unreadable image: {image_path}", file=sys.stderr)
            continue

        t0 = time.time()
        candidates = reader.read(image)
        latency_ms = (time.time() - t0) * 1000

        best = max(candidates, key=lambda c: c.mean_confidence, default=None)
        rows.append(
            EvalRow(
                image_path=image_path,
                ground_truth=ground_truth,
                predicted=best.text if best else None,
                plate_confidence=best.mean_confidence if best else 0.0,
                latency_ms=latency_ms,
            )
        )

    _report(rows)


def _report(rows: list[EvalRow]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVIDENCE_DIR / "anpr-accuracy.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "image_path",
                "ground_truth",
                "predicted",
                "exact_match",
                "char_accuracy",
                "latency_ms",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.image_path,
                    row.ground_truth,
                    row.predicted or "",
                    row.exact_match,
                    f"{row.char_accuracy:.3f}",
                    f"{row.latency_ms:.1f}",
                ]
            )

    exact_match_rate = sum(1 for r in rows if r.exact_match) / len(rows)
    detected_rate = sum(1 for r in rows if r.predicted is not None) / len(rows)
    mean_char_accuracy = statistics.mean(r.char_accuracy for r in rows)
    mean_latency = statistics.mean(r.latency_ms for r in rows)

    print(f"\nn = {len(rows)}")
    print(f"detected (a plate was read at all): {detected_rate:.1%}")
    print(f"exact-match plate accuracy:         {exact_match_rate:.1%}")
    print(f"mean character-level accuracy:      {mean_char_accuracy:.1%}")
    print(f"mean latency:                       {mean_latency:.1f} ms")
    print(f"\nfull results written to {out_path}")
    print(
        "\nCompare against docs/02-ANPR-PIPELINE.md section 7's accuracy-engineering "
        "checklist. If exact-match accuracy is below ~85% on legible plates, that is "
        "the fine-tuning decision gate described in docs/05-DELIVERY-PLAN.md M2."
    )


if __name__ == "__main__":
    main()
