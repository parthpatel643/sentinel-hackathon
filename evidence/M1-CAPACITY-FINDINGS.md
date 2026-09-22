# M1 Capacity Benchmark — Findings

**Status: infrastructure complete and verified. Absolute numbers from this session are NOT
authoritative — re-run required on a dedicated, idle machine (see §4).**

## 1. What was built and verified

- `services/edge_agent/src/edge_agent/pipeline/capture.py` — `RtspCapture`, wrapping OpenCV's
  FFmpeg backend exactly as the organisers' own reference snippet does (`OPENCV_FFMPEG_CAPTURE_OPTIONS
  = "rtsp_transport;tcp"`), converting `CAP_PROP_POS_MSEC` into `StreamClock` timing.
- `services/edge_agent/src/edge_agent/pipeline/supervisor.py` — `CameraSupervisor`, the
  per-camera reconnect state machine (exponential backoff 2s→30s with jitter, circuit
  breaker on sustained read failure, never raises out of a connection problem).
- `scripts/synthetic_grid.py` — an 8-camera, mixed-codec (H.264/H.265), mixed-resolution
  (360p→1080p), mixed-frame-rate (8–30 fps) local test grid, publishing into a dev/*-scoped
  path on the same MediaMTX relay the production design uses. Verified to reproduce the
  organisers' own documented quirks (join-time decoder warnings, scene-cut-on-loop) faithfully.
- `scripts/bench_capacity.py` — ramps N concurrent RTSP decode sessions, scores each stream
  against **its own declared rate** (a "keep-up ratio"), and reports the largest N before a
  meaningful fraction of individual streams degrade. This was a deliberate redesign after an
  early version used a global mean, which hid a real per-stream stall behind a healthy-looking
  average — see §3.
- 89 unit/integration tests across `packages/sentinel_core` and `services/edge_agent`, plus the
  automated integrator-compliance suite, all passing (`make check`).

## 2. Measured data (this session, M2, heavily contended — see §4)

| n_cameras | opened | degraded | mean keep-up | min keep-up |
|---|---|---|---|---|
| 2 | 2 | 0 | 96.6% | 85.6% |
| 4 | 4 | 0 | 100.3% | 73.5% |
| 6 | 6 | 3 | 59.0% | 1.2% |

A later re-run (same machine, ~15 minutes later, after other load on the host had increased)
showed degradation starting as low as n=2. Raw CSVs are in this directory
(`capacity-<host>-<timestamp>.csv`).

## 3. A real bug the tool caught in itself

The first version of `bench_capacity.py` scored each ramp step by a **global mean** achieved
fps against a fixed target. At n=8 that run showed `mean=280%, min=0.12 fps` — the mean looked
extremely healthy while at least one stream had almost completely stalled (~1 frame per 8
seconds). A global mean is the wrong statistic for a capacity ceiling: it is dragged up by the
healthy majority and hides exactly the failure mode that matters (a handful of cameras going
dark while a dashboard's average tile still looks green). The benchmark was rewritten to score
per-stream against **that stream's own declared rate** and to gate on **the fraction of
individually degraded streams**, not a mean. This is now also the intended design for the
production health dashboard — an aggregate "system healthy" tile must never be allowed to hide
a specific camera going dark.

## 4. Why the absolute numbers here are not the final answer

This session's benchmarks ran on a **shared, multi-tenant host, not a dedicated machine**:

- `docker stats` during these runs showed containers from an **unrelated project** (`sentinel-hackathon-astra-backend-1`, `sentinel-hackathon-astra-db-1`) that this session did not create, confirming other tenants' workloads were concurrently active on the same box.
- System load average was ~5.2 (on an 8-core M2) with several GB of memory under compression, indicating significant contention from processes entirely outside this benchmark's or this repository's control.
- The synthetic grid's own 8 publisher processes and the MediaMTX relay also compete for the same CPU as the consumers being measured — itself a known, documented, and deliberate conservative bias (see the module docstring in `bench_capacity.py`) even on an *idle* machine, and compounded further by the above.

Two independent isolation experiments during this session (disabling hardware acceleration;
reducing the synthetic grid to 3 publishers) each changed the numbers without resolving the
noise, consistent with the bottleneck being host-level contention outside this process's
control rather than a defect in the capture harness. A solo camera, run outside any concurrent
ramp, decoded correctly and at its full declared rate every time — confirming the harness
itself is correct; it is the *concurrent, shared-host* measurement that is unreliable here.

## 5. What to do next

Re-run this exact benchmark on a machine dedicated to the demo, with nothing else competing
for CPU:

```bash
make up
uv run python scripts/synthetic_grid.py all
uv run python scripts/bench_capacity.py --min-cameras 4 --max-cameras 48 --step 4 --duration 10
```

Do this once on the M2 and once on the M4 (both mentioned in the solution plan as available
demo hardware), close other applications first, and check `uptime` / `docker stats` beforehand
to confirm the machine is actually idle. Commit the resulting CSVs to `evidence/` and update
the tiering numbers in `docs/01-ARCHITECTURE.md` §4.3 and `docs/02-ANPR-PIPELINE.md` §6 to cite
the clean run instead of this one.

The tool, the synthetic grid, and the capture/supervisor code are the M1 deliverable and are
complete; the clean number is a five-minute follow-up whenever a quiet machine is available.
