# ANPR accuracy on a hand-labelled Gujarat holdout

**Measured: 1 October 2026, on the base M2; re-measured 12 October 2026 on the
same holdout after the plate-format change in `aec10b7`** (see
[Re-measured 12 October](#re-measured-12-october)). Reproduce with:

```bash
uv run --package edge-agent python scripts/build_anpr_holdout.py   # crops (not committed)
uv run --package edge-agent python scripts/eval_anpr.py evidence/anpr-holdout-labels.csv
```

## Headline

| Measure (legible plates only) | Result |
|---|---|
| Exact plate, single crop | **65.4%** (53 of 81) |
| Exact plate, single crop, averaged per vehicle | **73.9%** (42 vehicles) |
| Exact plate after the pipeline's multi-frame vote | **80.5%** (33 of 41 vehicles) |
| Found by the search ladder's exact or OCR-ambiguity rung | **66.7%** |
| Character-level accuracy | **88.6%** |
| A plate was read at all | 98.8% |
| Mean detector + OCR latency per crop, CPU | 49 ms (1 Oct, idle machine) |

That is below the ~85% fine-tuning gate in `docs/05-DELIVERY-PLAN.md` M2, and
we say so. Before this measurement the configured model read **8.6%**; the
fixes below came out of the measurement itself.

## Method

1. `scripts/build_anpr_holdout.py` ran the plate detector over stored
   detection snapshots from the live government camera grid and wrote, per
   plate found, the context crop the reader is given and a zoomed view.
2. Every crop was labelled by a person from the zoomed view, **blind to the
   OCR output**. A plate was labelled only when every character was
   readable with high confidence; otherwise `UNREADABLE`. Plate grammar was
   **not** used to fill in a blurred character (an early attempt to do so was
   wrong and was reverted).
3. 160 crops: **79 were unreadable to a person** and are excluded from
   scoring; they are what a 20–26 px tall plate on a wide-area camera looks
   like. 81 legible crops of 42 distinct plates remain (3 are two-row plates).
4. `scripts/eval_anpr.py` reads each legible crop through the production
   `FastAlprPlateReader`, applies the same grammar correction as
   `analytics/voting.py`, and writes every read to `evidence/anpr-accuracy.csv`.

The camera footage is consume-only, so the crops stay in the gitignored
`data/anpr-holdout/`. Only labels and results are committed.

## What changed, and how each change was checked

Each variant was scored on the full set **and on two halves split by vehicle**,
so a change counts only if it helps vehicles it was not tuned on.

| Configuration | Exact (all 80 detected) | Half A | Half B |
|---|---|---|---|
| `cct-s-v2` OCR, detector box as-is (previous default) | 7 | — | — |
| `cct-xs-v2` OCR | 30 | 19 | 11 |
| + 10% / 15% box padding | 35 | 16 | 19 |
| + Indian-grammar letter/digit correction | **53** | 27 | 26 |

- **OCR model.** `cct-xs-v2` (the library's own default) read four times as
  many plates exactly as `cct-s-v2` on this footage, and is about six times
  faster. `cct-s-v1` and `global-plates-mobile-vit-v2` were worse than both.
- **Padding.** The detector's box clipped the last character of small
  plates. Padding alone helped one half and hurt the other; with grammar
  correction it helped both, so it was kept.
- **Grammar correction** (`sentinel_core.plates.correct_plate_grammar`). Where
  the standard format `SS DD L{1,3} NNNN` needs a digit and the OCR produced
  a confusable letter (`GJQ3…`), or the reverse, the character is swapped
  within its ambiguity class. It never touches a valid read, never invents a
  missing character, and never changes the plate's ambiguity key, so a
  corrected read lands on the same matching rung as before. It is applied to
  each read before the vote, so `GJQ3…` and `GJ03…` from two frames agree.

## Re-measured 12 October

The same 81 legible crops, read again with the code at `aec10b7`. The OCR's
raw read is identical on every crop; what changed is what happens after it.
That commit widened the valid plate format to numbers of one to four digits
(older plates print `GJ 5 CD 12`), restricted grammar correction to the
four-digit layout, and made the voter prefer a full four-digit read over a
shorter one that could be a truncation.

| Measure | 1 Oct | 12 Oct |
|---|---|---|
| Exact, single crop | 65.4% | 65.4% |
| Exact, averaged per vehicle | 73.9% | 73.9% |
| Exact after the vote | 78.0% (32 of 41) | **80.5% (33 of 41)** |
| Character-level accuracy | 88.0% | **88.6%** |

Three crops changed, all by no longer being "corrected" into the wrong
layout: `GJ3ZAG288` had been forced to `GJ3ZA6288`, `GJ25AA43` to
`GJ2S4443`, `GJ11CD119` to `GJ11C0119`. None became exact; their characters
did, and the vote gained one vehicle. The gain is one vehicle in 41: real,
but small, and still below the 85% gate.

`evidence/anpr-accuracy.csv` is the 12 October run. It was taken while an
edge worker was analysing cameras on the same machine, so its per-crop
latencies (about 100 ms) measure contention, not the reader; the 49 ms in
the headline is the 1 October run on an idle machine.

## What still goes wrong (28 misread crops)

| Class | Examples (truth → read) | Note |
|---|---|---|
| Valid-looking glyph confusion | `GJ32X9985 → GJ32K9985`, `GJ01HM7952 → GJ01HW7952`, `2783 → 2733` | Grammar cannot catch these; the edit-distance rung of search still finds the vehicle |
| Wrong length | `GJ15CB2934 → 515CB2934`, `GJ05RC9803 → GJ05RRC983` | Voting across a track's frames resolves most |
| `J`/`3` in the district number | `GJ03ME9186 → GJ0JME9186` | Not an ambiguity pair today, deliberately |
| Truncated | `GJ11CH3274 → G11EMM32` | Plate partly occluded |
| Not detected | `GJ03BZ1174` | 1 crop |

## Limits of this number

- **One camera dominates.** Most snapshots come from one Junagadh camera
  (Madhuram Bypass). Other angles, night footage and rain are not covered.
- **Plates the detector found.** A plate the detector missed never became a
  crop, so this measures reading, not finding.
- **Small sample.** 81 crops / 42 vehicles. Each vehicle is about 2.4 points.
- **The vote is approximated.** Crops of one plate stand in for one track's
  frames; a live track gives the voter five to fifteen reads, not one to three.

The next lever is fine-tuning `cct-xs-v2` on Indian plates
(`docs/02-ANPR-PIPELINE.md` section 4.1), with this holdout kept out of
training so it remains a fair test.
