# Analytics capacity per tier, measured end to end

**Measured: 1 October 2026, base M2 (8 cores), while the API, Postgres, the relay and
the web dev server ran on the same machine.** Raw rows: [`tier-capacity-m2.csv`](./tier-capacity-m2.csv).
Reproduce, on any machine:

```bash
make up && make api      # and `make seed` once
uv run --package core_api python scripts/measure_tier_capacity.py --tier b_sampled --cameras 2 4 6
uv run --package core_api python scripts/measure_tier_capacity.py --tier b_sampled --sampled-fps 4 --cameras 4 6
uv run --package core_api python scripts/measure_tier_capacity.py --tier a_continuous --cameras 1
```

## Method

`scripts/measure_tier_capacity.py` measures the real worker, not a benchmark loop:

- N 1080p25 H.264 streams of two vehicles crossing the frame every 12 s, one
  with a `GJ01AB1234` plate, published on the local relay's `dev/` paths.
  The government grid is never used, because its watch-time quota is
  account-wide.
- The cameras are registered in the registry with the tier under test and
  analysed by `edge_agent.worker --source registry`, exactly as on site.
- Analysed fps, analysis lag and status come back through `GET /api/v1/cameras`,
  the same figures the Cameras and Health screens show. Worker CPU is the
  summed `%CPU` of its process tree.
- **Keeps up** = every camera live, analysed fps ≥ 80% of target, and lag
  over the last third of the run under 5 s. Lag that keeps growing means the
  worker reads the stream slower than real time.

The scene is deliberately dense: a vehicle, and a plate to read, in nearly every
analysed frame. Real junctions are emptier, so these are floors.

## Results

Every recorded run (`tier-capacity-m2.csv`). Repeats of the same configuration are
listed separately; how far they differ is the point.

| Tier | Analysis rate | Cameras | Analysed fps | Lag at end | Worker CPU | Verdict |
|---|---|---|---|---|---|---|
| B sampled | 8 fps | 2 | 8.0 | 1.0 s | 369% | keeps up |
| B sampled | 8 fps | 2 | 8.0 | 7.0 s | 410% | falls behind |
| B sampled | 8 fps | 4 | 8.0 | 18.9 s, growing | 567% | falls behind |
| B sampled | 4 fps | 4 | 4.0 | 1.0 s | 507% | keeps up |
| B sampled | 4 fps | 6 | 4.0 | 21.9 s, growing | 654% | falls behind |
| A continuous | 25 fps (stride 1) | 1 | 25.0 | 10.5 s, growing | 233% | falls behind |
| A continuous | 8.3 fps (stride 3) | 1 | 8.3 | 0.1 s | 197% | keeps up |
| A continuous | 8.3 fps (stride 3) | 2 | 8.3 | 46.0 s | 261% | falls behind |
| A continuous | 8.3 fps (stride 3) | 2 | 7.1 | 2.6 s | 367% | keeps up, dropping frames |

**Rule of thumb for the M2: about 16 analysed frames per second of dense traffic in
total, and that is the edge, not a safe margin.** Two cameras at about 8 fps kept up in
some runs and not in others; four at 4 fps kept up. One camera at 8 fps always kept up.
The M2 was also running the API, Postgres, the Docker VM and the web dev server, as it
would on site. Tier A at a full 25 fps does not fit one camera's serial pipeline (about
12.7 analysed fps on this scene); run tier A with `STRIDE=3`.

For the finale, plan to about **75% of the measured edge**: on the M2 that is one
camera at 8 fps plus a few at 4 fps, or everything at 4 fps.

## What limits it, and what changed because of this measurement

The plate detector is the cost: about 50 ms per vehicle on CPU, against 11 ms
for vehicle detection and 2.3 ms to decode a 1080p frame. It tops out near
**30 plate reads per second** on the M2 however its threads are arranged. The
first run of this tool showed two cameras at 8 fps **falling behind**
(25 s lag). Three changes followed, each measured:

1. **A settled plate is not re-read on every frame**
   (`analytics/voting.py`). Once a track's vote is valid and unanimous over six
   reads, it is re-checked only every 8th analysed frame. A track still
   unreadable after 24 attempts is read every 3rd frame. A vehicle that passes
   in the usual one to three seconds is read on every frame. This took two
   cameras from 25 s lag to 0.4 s.
2. **Two ONNX Runtime threads per plate inference, no spin-waiting**
   (`analytics/plate_reader.py`). With four concurrent callers: 30.0 reads/s
   at 504% CPU, against 27.5 reads/s at 687% with the default.
3. The OCR model change from the accuracy work (`cct-xs-v2`) is also about six
   times cheaper than the previous `cct-s-v2`.

A smaller plate-detector input (384 px) would double plate throughput. On the
labelled holdout it read 52 plates against 53 at 640 px, but 416 px read 46, so
the evidence is too noisy to trade accuracy for it. It stays at 640 px.

## Expectations for the M4 (to be measured in UAT)

The M4 has more and faster cores. Measure it with the commands above rather than
extrapolating from these figures, then set `SAMPLED_FPS` and tiers to match
(runbook §6). For the finale:

- Run the cameras the designated vehicle is likely to pass at **tier A with
  `STRIDE=3`** or **tier B at 8 fps**.
- Run the rest at **4 fps** or **motion-gated**, and anything beyond capacity at
  **tier D** (view-only).
- Watch the Cameras screen. A red `n s behind live` that keeps growing means
  lower the rate or move a camera down a tier.
