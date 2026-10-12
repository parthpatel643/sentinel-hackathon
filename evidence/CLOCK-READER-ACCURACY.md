# Reading the camera's clock: PP-OCRv6 replaces Tesseract

**Measured: 12 October 2026, on the base M2 (CPU only).** Every sighting is
reported with the time the camera burned into its own frame, so how often that
clock is read, and how rarely it is misread, decides how many sightings land
on a timed route and whether any of them carry a wrong time.

## Headline

| Measure | Tesseract (before) | PP-OCRv6 (now) |
|---|---|---|
| Exact timestamp, single frame, legible clocks (87 frames) | 69.0% (60) | **97.7% (85)** |
| Wrong timestamp, single frame, legible clocks | 1 | **0** |
| Stream-seconds with a verified time, all 30 grid cameras replayed | 12.8% | **37.4%** |
| Cameras with any verified time | 14 of 30 | **23 of 30** |
| Verified times inconsistent with their neighbours | 11 of 807 (1.4%) | **18 of 2,622 (0.7%)** |
| CPU per stream-second of a camera | 88 ms | **29 ms** |
| First read of a camera (detect + recognise), median | 693 ms | **132 ms** |
| Each later read (recognise the known box), median | (same full scan) | **~21 ms** |
| System dependency | `brew install tesseract` | none (models ship in the `rapidocr` wheel) |

## Reproduce

```bash
# 1. Build the holdout (frames stay under data/, gitignored)
uv run --package edge-agent python scripts/build_clock_holdout.py
# 2. Label data/clock-holdout/sheets/ by hand (rules: data/clock-holdout/LABELLING.md);
#    the labels used here are evidence/clock-holdout-labels.csv
# 3. Single-frame accuracy
uv run --package edge-agent python scripts/eval_clock.py data/clock-holdout/labels.csv \
    --engine production --engine production-tracked
# 4. Production behaviour over recorded streams (verification included)
uv run --package edge-agent python scripts/replay_clock.py --seconds 90
# The Tesseract figures: pass the previous reader's source (git show 5ab1d95:services/edge_agent/src/edge_agent/analytics/frame_clock.py)
# as --reader-module / CLOCK_TESSERACT_MODULE with `--with pytesseract`.
```

## Method

**Holdout.** `scripts/build_clock_holdout.py` sampled 158 whole frames with a
fixed seed: four from each of the 30 recordings in the government-grid mirror,
spread through each recording, plus 40 detection snapshots the live pipeline
had stored for the two cameras that produced sightings (cam06 and cam30),
half of which the Tesseract reader had verified and half it had not. Each
frame's top and bottom edges were tiled into numbered sheets **with no OCR
output on them**.

**Labels.** Two independent passes labelled every frame from the sheets alone,
in opposite orders, under strict rules: a timestamp only when every digit is
legible with high confidence, otherwise `UNREADABLE`; no digit inferred from
context. They agreed on 150 of 158. All 8 disagreements were "readable" against
"unreadable", never two different times; each was adjudicated at full
resolution (4 readable, 4 unreadable). Result: **87 frames with a legible
clock** from 23 cameras, and 71 without one (no overlay, or a digit destroyed
by compression).

**Scoring.** `scripts/eval_clock.py` gives each engine one frame at a time,
with no memory, so it measures what a single frame yields. *Wrong* means a
plausible timestamp that is not the label: the dangerous outcome.

**Replay.** `scripts/replay_clock.py` feeds two 90-second windows of every
recording (5,220 stream-seconds in all) through the reader exactly as the
worker does: frames in stream order with their own presentation times, the
clock read at most once a stream second, and each reading counted only once
`FrameClockReader.verified()` confirms it, checked three seconds after it was
taken, as when a sighting is emitted. Ground truth is not available for every
second, so a verified time is flagged as *inconsistent* when it disagrees with
both neighbouring verified times: a clock may stall, but it cannot run
backwards or faster than the footage. A flag is an upper bound on wrong
times: some flags are a recording's own jumps, which this cannot tell apart.

## What changed in the reader

- **Engine.** PP-OCRv6 small detection and recognition models (ONNX, run by
  ONNX Runtime through `rapidocr`), loaded once per worker process and shared
  by every camera.
- **Find once, then recognise only.** The first read of a camera runs text
  detection over the frame's top and bottom bands and assembles the clock from
  the boxes on its row (date, time, AM/PM, weekday), leaving camera names out.
  The box is remembered; later reads only recognise that crop. A failing box
  falls back to a full scan every 30 s, as before.
- **The detector's input is capped by its long side (960 px).** The library
  default scales a band's short side up, turning a 1920×140 strip into about
  10,000 px of input. Measured on the holdout with the evaluation harness's
  simpler line-joining, the cap was faster *and* more accurate (640 and
  960 px: 98.9%; 1280 px: 97.7%; 1920 px: 95.4%). 960 px was kept as the
  larger of the two best.
- **AM/PM read as part of the clock.** On 12-hour cameras the model can return
  `PM` as its own box. Read without it, 09:00 PM parses as the morning, which
  is exactly a confident wrong time. The parts are joined before parsing.
- **Confirmation must come from another tick of the overlay** (new rule, both
  readers would have benefited). Replay found frames 40 ms apart that showed
  the same digit damaged the same way by the same compression block, read the
  same wrong second, and confirmed each other. Readings less than 0.9 s of
  footage apart are now one observation. Cost: 0.2 points of coverage in a
  replay of all 30 cameras.
- **Agreement tolerance 3 s → 2 s.** Replayed on the six cameras with the most
  flags, it rejected a quarter of the inconsistent readings (19 → 14) for 1.3
  points of coverage. The overlay ticks once a second, so 2 s keeps a full second of
  margin.

## What it still cannot do, and why

- **The model reads damaged digits with full confidence.** On the 71
  unreadable frames, it produced a time on 22 (Tesseract on 5). Its confidence
  on those (median 0.992) is indistinguishable from legible ones (median
  0.998), so no threshold separates them. Cross-frame verification, not
  confidence, is what keeps them out of evidence, and is why verification was
  tightened rather than relaxed.
- **cam30 and cam06, the two cameras with live sightings, are limited by
  their streams, not OCR.** The grid delivers cam30 at 3 fps with 80% of its
  footage missing, and cam06 with 75% missing and H.265 decode damage. On the
  stored snapshots of theirs that Tesseract left unverified, a single-frame
  read was already right 17 of 19 times; what failed was finding a second,
  agreeing reading. Replayed, cam30 is the one camera where the new reader
  verifies less (32.0% → 28.0%), from the stricter confirmation rules.
- **Seven cameras have no legible clock in their recordings at all** (cam10,
  cam14, cam16 to cam19, cam23): no overlay, or one destroyed by compression.
  No reader can help there; their sightings remain *time unknown*.

## Files

- `evidence/clock-holdout-labels.csv`: the 158 labels (frames are not
  committed: the organisers' footage is consume-only).
- `evidence/clock-holdout-results.csv`: every engine's read of every frame.
- `evidence/clock-replay.json`, `evidence/clock-replay-tesseract.json`:
  per-camera replay results.
