#!/usr/bin/env python3
"""ANPR accuracy evaluation against a labelled holdout.

Per docs/02-ANPR-PIPELINE.md section 7: no public benchmark with real Indian
plate data exists, so a holdout you build yourself from your own cameras is
the only way to state an accuracy number honestly. This script computes that
number once you have one; it does not fabricate one.

Expected input: a CSV with columns `image_path,ground_truth_plate`, where
each image is a single-vehicle or plate-region crop. `ground_truth_plate` may
be `UNREADABLE` for a plate a person could not read either: those rows are
counted and reported, never scored. An optional `layout` column
(one_row | two_row) adds a per-layout breakdown. Image paths are relative to
the repository root. `scripts/build_anpr_holdout.py` produces such a file.

Usage:
    uv run --package edge-agent python scripts/eval_anpr.py evidence/anpr-holdout-labels.csv
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
UNREADABLE = "UNREADABLE"


@dataclass(slots=True)
class EvalRow:
    image_path: str
    ground_truth: str
    predicted: str | None
    raw_read: str | None
    plate_confidence: float
    latency_ms: float
    layout: str = "one_row"

    @property
    def exact_match(self) -> bool:
        return self.predicted == self.ground_truth

    @property
    def raw_exact_match(self) -> bool:
        return self.raw_read == self.ground_truth

    @property
    def ambiguity_match(self) -> bool:
        """Found by the search's OCR-ambiguity rung even when not exact."""
        from sentinel_core.plates import ambiguity_key

        return self.predicted is not None and ambiguity_key(self.predicted) == ambiguity_key(
            self.ground_truth
        )

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


def _read_holdout(path: Path) -> list[tuple[str, str, str]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"image_path", "ground_truth_plate"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            print(f"CSV must have columns: {sorted(required)}", file=sys.stderr)
            raise SystemExit(1)
        return [
            (
                row["image_path"],
                row["ground_truth_plate"].strip().upper(),
                (row.get("layout") or "one_row").strip(),
            )
            for row in reader
        ]


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(1)
    holdout_path = Path(sys.argv[1])
    if not holdout_path.exists():
        print(f"no such file: {holdout_path}", file=sys.stderr)
        raise SystemExit(1)

    import cv2

    from edge_agent.analytics.plate_reader import FastAlprPlateReader, PlateCandidate
    from edge_agent.analytics.voting import PlateVoter
    from sentinel_core.plates import correct_plate_grammar, normalise_plate

    all_entries = _read_holdout(holdout_path)
    entries = [e for e in all_entries if e[1] != UNREADABLE]
    if not entries:
        print("holdout file has no readable ground truth", file=sys.stderr)
        raise SystemExit(1)

    print(f"loading OCR model, evaluating {len(entries)} legible entries ...")
    reader = FastAlprPlateReader()
    rows: list[EvalRow] = []
    reads_by_plate: dict[str, list[PlateCandidate]] = {}
    for image_path, ground_truth, layout in entries:
        image = cv2.imread(str(REPO_ROOT / image_path))
        if image is None:
            print(f"  skipping unreadable image: {image_path}", file=sys.stderr)
            continue
        t0 = time.time()
        candidates = reader.read(image)
        latency_ms = (time.time() - t0) * 1000
        best = max(candidates, key=lambda c: c.mean_confidence, default=None)
        raw = normalise_plate(best.text) if best else None
        if best:
            reads_by_plate.setdefault(normalise_plate(ground_truth), []).append(best)
        rows.append(
            EvalRow(
                image_path=image_path,
                ground_truth=normalise_plate(ground_truth),
                # Corrected exactly as analytics/voting.py does before voting.
                predicted=correct_plate_grammar(raw) if raw else None,
                raw_read=raw,
                plate_confidence=best.mean_confidence if best else 0.0,
                latency_ms=latency_ms,
                layout=layout,
            )
        )

    voted_right = 0
    for plate, reads in reads_by_plate.items():
        voter = PlateVoter()
        for read in reads:
            voter.add(read)
        resolved = voter.resolve()
        voted_right += resolved is not None and resolved.plate_normalised == plate
    _report(rows, unreadable=len(all_entries) - len(entries), total=len(all_entries))
    print(
        f"\nvoted across each plate's crops with the pipeline's PlateVoter: "
        f"{voted_right}/{len(reads_by_plate)} plates exact "
        f"({voted_right / len(reads_by_plate):.1%}). Crops of one plate stand in for "
        "the frames of one track; most plates here have one to three crops, where a "
        "live track gives the voter five to fifteen."
    )


def _rate(rows: list[EvalRow], attr: str) -> float:
    return sum(1 for r in rows if getattr(r, attr)) / len(rows) if rows else 0.0


def _per_vehicle(rows: list[EvalRow]) -> tuple[int, float]:
    """Consecutive frames repeat the same vehicle; score each distinct plate
    by the share of its crops read exactly, then average across plates."""
    by_plate: dict[str, list[EvalRow]] = {}
    for row in rows:
        by_plate.setdefault(row.ground_truth, []).append(row)
    return len(by_plate), statistics.mean(_rate(g, "exact_match") for g in by_plate.values())


def _report(rows: list[EvalRow], *, unreadable: int, total: int) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVIDENCE_DIR / "anpr-accuracy.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "image_path",
                "ground_truth",
                "raw_read",
                "predicted",
                "exact_match",
                "ambiguity_match",
                "char_accuracy",
                "plate_confidence",
                "layout",
                "latency_ms",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.image_path,
                    row.ground_truth,
                    row.raw_read or "",
                    row.predicted or "",
                    row.exact_match,
                    row.ambiguity_match,
                    f"{row.char_accuracy:.3f}",
                    f"{row.plate_confidence:.3f}",
                    row.layout,
                    f"{row.latency_ms:.1f}",
                ]
            )

    vehicles, per_vehicle = _per_vehicle(rows)
    read_rate = sum(1 for r in rows if r.predicted) / len(rows)
    char_accuracy = statistics.mean(r.char_accuracy for r in rows)
    latency = statistics.mean(r.latency_ms for r in rows)
    lines = [
        f"plates in holdout:                   {total}",
        f"  unreadable to a person (excluded): {unreadable}",
        f"  scored (legible):                  {len(rows)} crops of {vehicles} distinct plates",
        f"read at all:                         {read_rate:.1%}",
        f"exact match, raw OCR read:           {_rate(rows, 'raw_exact_match'):.1%}",
        f"exact match, after grammar fix:      {_rate(rows, 'exact_match'):.1%}",
        f"found by exact or ambiguity rung:    {_rate(rows, 'ambiguity_match'):.1%}",
        f"exact match, averaged per vehicle:   {per_vehicle:.1%}",
        f"mean character-level accuracy:       {char_accuracy:.1%}",
        f"mean latency per crop:               {latency:.1f} ms",
    ]
    for layout in sorted({r.layout for r in rows}):
        subset = [r for r in rows if r.layout == layout]
        lines.append(
            f"  {layout:<8} n={len(subset):<3} exact {_rate(subset, 'exact_match'):.1%}  "
            f"exact-or-ambiguity {_rate(subset, 'ambiguity_match'):.1%}"
        )
    print()
    print("\n".join(lines))
    print("\nmisreads (ground truth -> read):")
    for row in rows:
        if not row.exact_match:
            print(f"  {row.ground_truth:<12} -> {row.predicted or '(nothing)'}")
    print(f"\nfull results written to {out_path}")
    print(
        "\nCompare against docs/02-ANPR-PIPELINE.md section 7's accuracy-engineering "
        "checklist. If exact-match accuracy is below ~85% on legible plates, that is "
        "the fine-tuning decision gate described in docs/05-DELIVERY-PLAN.md M2."
    )


if __name__ == "__main__":
    main()
