# M2 Finding — the synthetic grid does not reproduce a live PTS discontinuity

**Status: known limitation, does not affect correctness of the discontinuity-handling
code itself (that is unit-tested directly and passes). Affects only end-to-end
integration-level exercising of that path against our own local test fixture.**

## What was expected

`scripts/synthetic_grid.py` publishes each camera's clip on a loop via
`ffmpeg -re -stream_loop -1 -i clip.mp4 -c copy -f rtsp ...`, on the premise (stated in
that script's own docstring) that looping a short clip would let development exercise the
organisers' documented "scene discontinuity" behaviour: *"Each feed is a continuous
recording that loops. At the loop point the scene cuts abruptly, similar to a camera
reboot."*

## What was actually measured

Running a capture against `dev-cam-01` (a 12-second clip) for 600 frames (~24 seconds,
i.e. well past two loop points) showed the PTS reported via `CAP_PROP_POS_MSEC` climbing
smoothly and monotonically past 25,700 ms with **no reset and no jump greater than
100 ms** at any point.

```
final pts: 25720.0  # after 600 frames of a 12,000 ms clip — should have looped twice
```

**Root cause:** ffmpeg's `-stream_loop` input option is explicitly designed to make
looped playback *seamless* — it renumbers timestamps to be continuous across loop
iterations rather than resetting them. This is the correct, intended behaviour for
looping ffmpeg's own playback, but it means our synthetic grid does not reproduce a
live, over-the-wire PTS discontinuity the way the real government grid's own encoder
does (their loop point is a genuine scene cut with resetting timestamps, since it is
presumably implemented differently — as a fresh recording restart, not an ffmpeg
playback loop flag).

## Why this is not a correctness gap in the pipeline

`sentinel_core.clock.StreamClock`'s discontinuity detection is unit-tested directly
against constructed PTS sequences (`packages/sentinel_core/tests/test_clock.py`),
including exact reproductions of a loop-cut, a large forward jump, and B-frame
reordering vs a genuine cut. Those tests exercise the *logic* correctly and pass. The
`AnprPipeline` correctly calls `tracker.reset()` and clears vote history when
`frame.timing.is_discontinuity` is true — this is covered by
`test_stream_discontinuity_resets_vote_history` in
`services/edge_agent/tests/test_anpr_pipeline.py`, using a manually constructed frame
with `is_discontinuity=True`.

What is missing is **integration-level** proof that a real network capture session,
run against our own fixture for long enough to cross a loop point, actually surfaces
`is_discontinuity=True` from real PTS data. It does not, because the fixture's PTS never
discontinues.

## What was tried instead of just noting it and moving on

A full ffmpeg publisher restart (kill + relaunch of the process publishing to a given
`dev/*` path) was considered as an alternative way to force a PTS reset, since a brand
new ffmpeg process starts its own timestamp numbering at zero. This was not pursued
further within the time available, because it more likely reproduces a **connection
drop and reconnect** (already covered, and already tested, by
`CameraSupervisor`'s backoff logic in `test_supervisor.py`) rather than the specific
"stream stays connected, but the scene and its PTS numbering discontinue" case the
organisers describe.

## What to do about it

1. **Nothing changes about confidence in the shipped discontinuity-handling code** — it
   is directly unit-tested and correct in isolation.
2. **The real government grid will exercise this path for real.** Their integrator guide
   states the loop-cut behaviour explicitly as something evaluators should expect, which
   is strong evidence their gateway resets timestamps at the loop point (unlike our
   ffmpeg-based fixture). The first live run against the government grid is the actual
   integration test for this path, and should be watched for a `stream.discontinuity`
   event / a `clock.discontinuities` counter increment on the health dashboard as
   confirmation.
3. **If a faithful local reproduction becomes worth the time later**, the correct fix is
   not a simple flag — it requires either (a) a custom small RTSP source that explicitly
   resets PTS at a scene boundary (more test-fixture code), or (b) re-encoding each loop
   iteration with `-fflags +genpts` combined with explicitly zeroing the muxer's timestamp
   offset per loop, which needs verifying against ffmpeg's loop-demuxer internals rather
   than assumed. Not done here; flagged as a possible improvement, not a blocker.

---

## Addendum — real end-to-end pipeline verification (same session)

Beyond the discontinuity finding above, the full ANPR pipeline (vehicle detector → SORT-
style tracker → plate detector → OCR → temporal voting → validated event) was verified
three independent ways, all with the REAL open-source models (not mocks):

1. **Static-image smoke test** (`scripts/smoke_test_anpr.py`) against a real photograph
   (a bundled fast-alpr test asset — no Indian plate available locally yet, see the
   eval-set gap below): correctly detected a vehicle, cropped its ROI, detected and read
   the plate (`5AU5341`, confidence 1.000), and emitted a fully-provenanced event.
2. **Live-capture integration test**: fed 500 real frames from the synthetic grid's
   `dev-cam-01` (mixed codec, real RTSP/PTS path, not a static image) through the full
   pipeline with zero crashes. Zero plate events is correct and expected — the synthetic
   grid's `testsrc` content contains no real vehicles.
3. **Throughput measurement**: the full chain (vehicle detect + SORT tracker + plate
   detect + OCR, one vehicle/frame) sustains **~14.7 fps (67.9 ms/frame)** on this base
   M2, single-threaded, CoreML EP for both detectors and CPU EP for OCR (per the pinned
   execution-provider policy in docs/02-ANPR-PIPELINE.md section 3). This is the
   pipeline-level number to combine with the per-model figures already in that
   document when sizing the M4 demo's per-camera analytic tier.

**What is still missing, honestly:** an actual accuracy number on real Indian plates.
`scripts/eval_anpr.py` is built and verified working (it correctly scored the one known
test image at 100% exact-match), but a single non-Indian sample is not an accuracy
report — collecting and hand-labelling a stratified holdout from real camera footage
(day/night, angle, distance, motion blur) per docs/02-ANPR-PIPELINE.md section 7 remains
the next concrete step before quoting any accuracy figure to a jury.

