#!/usr/bin/env python3
"""Local copy of the government camera grid.

The organisers' grid (`cctv.corp8.cloud`) serves each camera as an archived
recording replayed as a simulated live feed, and it is being taken down. This
keeps a copy: it records every camera's stream as sent (stream copy, never
re-encoded), stitches each camera's footage into one pass of its clip, and
replays that on a loop from the LOCAL MediaMTX relay under
`mirror/<camera_id>` — same ids, names and map positions — so the worker,
the console and every demo run without the remote.

    uv run python scripts/gov_mirror.py capture     # record every camera (resumable)
    uv run python scripts/gov_mirror.py assemble    # stitch one clip per camera + the catalogue
    uv run python scripts/gov_mirror.py start       # loop-publish the copy into the local relay
    uv run python scripts/gov_mirror.py status      # what the relay sees
    uv run python scripts/gov_mirror.py stop        # stop the publishers

`capture` is the only step that touches the remote. Run it again and it
continues where it stopped; everything after it is offline.

What the grid does to a recording, all measured against it:

- It meters watch time per account. When the quota runs out every stream is
  refused until a cooldown passes; capture pauses every camera and resumes
  by itself (`QuotaGate`).
- It drops connections every minute or two, and a camera's replay restarts
  from the top of its clip whenever it has had no viewer for a few seconds.
  So footage is placed by what it shows, not when it was recorded (see the
  assemble section), and few cameras are recorded at once, so each gets long
  unbroken stretches inside one quota window instead of every camera
  re-recording its first minutes after every cooldown.
- It sends what it sends: several cameras deliver a few frames a second of a
  nominal 25, and some H.265 cameras repeat their parameter sets, which
  MediaMTX refuses until the copy's metadata is de-duplicated
  (`_dedupe_hvcc`). The manifest records how much each camera failed to
  deliver.

What a copy cannot be. It holds what the capture recorded, not the whole
remote recording: a few continuous stretches of each camera's clip (the
manifest's `sections`), played back to back. Cuts land on keyframes. And it
is replayed with ffmpeg's `-stream_loop`, which renumbers timestamps
seamlessly, so the PTS reset at the remote's loop point is not reproduced
(see evidence/M2-SYNTHETIC-GRID-DISCONTINUITY-FINDING.md).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "sentinel_core" / "src"))

MIRROR_DIR = REPO_ROOT / "data" / "gov-mirror"
RAW_DIR = MIRROR_DIR / "raw"
CLIPS_DIR = MIRROR_DIR / "clips"
RAW_CATALOGUE_PATH = MIRROR_DIR / "catalogue.raw.json"
CATALOGUE_PATH = MIRROR_DIR / "catalogue.json"
MANIFEST_PATH = MIRROR_DIR / "manifest.json"
PIDS_PATH = MIRROR_DIR / "pids.json"

RELAY_RTSP_HOST = "127.0.0.1"
RELAY_RTSP_PORT = 8554
RELAY_API_URL = "http://127.0.0.1:9997"
# Matches the mirror/*-only credential in infra/compose/mediamtx.yml. A
# throwaway local-fixture login, path-scoped so it cannot touch any other path.
RELAY_PUBLISH_USER = "gov-mirror"
RELAY_PUBLISH_PASS = "gov-mirror-local-only"
MIRROR_PATH_PREFIX = "mirror"

SEGMENT_S = 60
# Thumbnail geometry for loop matching. Small on purpose: what identifies a
# moment of footage is where the traffic is, not fine detail, and small
# frames make an hours-long search cheap.
SIG_W, SIG_H = 32, 18
REF_START_S = 15  # skip the join, where the decoder is still settling
REF_WINDOW_S = 60
MIN_PERIOD_S = 120
# Accept a period only when its window matches this much better than a
# typical shift does, and two windows agree on it to within a few seconds.
MATCH_RATIO = 0.35
MATCH_MAX_ABS = 6.0
PERIOD_AGREEMENT_S = 3
# Keep recording this long past the detected loop, so the assembler has room
# to choose a seam and to fill reconnect gaps from the other pass.
LOOP_MARGIN_S = 120

logger = logging.getLogger("gov_mirror")


# --------------------------------------------------------------------------
# Runs and segments
# --------------------------------------------------------------------------
#
# A run is one ffmpeg connection. Runs are kept apart rather than laid on one
# wall-clock timeline, because the grid does not resume where a client left
# off: when its streaming service restarts it drops every client and every
# camera starts its clip again from the top, so footage after a reconnect can
# belong anywhere in the loop. Within a run the footage is continuous.


@dataclass(frozen=True, slots=True)
class Segment:
    path: Path
    start_s: float  # seconds since the start of its run
    duration_s: float

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


@dataclass(frozen=True, slots=True)
class Run:
    run_id: str
    started: float  # wall clock, epoch seconds
    segments: tuple[Segment, ...]

    @property
    def span_s(self) -> float:
        return self.segments[-1].end_s if self.segments else 0.0


def _camera_dir(camera_id: str) -> Path:
    return RAW_DIR / camera_id


# ffmpeg's MPEG-TS muxer starts every file's timestamps this far above zero.
TS_START_OFFSET_S = 1.4


def _media_extent(segment: Path) -> tuple[float, float]:
    """(seconds after the segment-list start at which the file's first frame
    sits, seconds of media it holds), cached beside the closed segment.

    The segment list alone overstates both: stream copy discards everything
    before the first keyframe, and one camera's first keyframe arrived 98 s
    into its connection — the list still said the segment began at 0.
    """
    cached = segment.with_suffix(".extent.json")
    if cached.exists():
        lead, duration = json.loads(cached.read_text())
        return float(lead), float(duration)
    fmt = _probe(segment, "format=start_time,duration").get("format", {})
    lead = max(0.0, float(fmt.get("start_time") or TS_START_OFFSET_S) - TS_START_OFFSET_S)
    duration = float(fmt.get("duration") or 0.0)
    cached.write_text(json.dumps([lead, duration]))
    return lead, duration


def camera_runs(camera_id: str) -> list[Run]:
    """Every run's closed segments — ffmpeg's segment list only names a
    segment once it has finished writing it."""
    path = _camera_dir(camera_id) / "runs.jsonl"
    if not path.exists():
        return []
    runs: list[Run] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        meta = json.loads(line)
        listing = _camera_dir(camera_id) / f"{meta['id']}.csv"
        rows = (
            [r for r in csv.reader(listing.read_text().splitlines()) if len(r) >= 3]
            if listing.exists()
            else []
        )
        segments: list[Segment] = []
        if rows:
            first_pts = float(rows[0][1])
            for name, start, _ in (r[:3] for r in rows):
                seg_path = _camera_dir(camera_id) / name
                if not seg_path.exists() or seg_path.stat().st_size == 0:
                    continue
                lead, duration = _media_extent(seg_path)
                if duration > 0:
                    segments.append(Segment(seg_path, float(start) - first_pts + lead, duration))
        runs.append(Run(meta["id"], meta["started"], tuple(segments)))
    return runs


# --------------------------------------------------------------------------
# Signatures + loop detection
# --------------------------------------------------------------------------


def _signature_path(segment: Path) -> Path:
    return segment.with_suffix(".sig.npy")


def segment_signature(segment: Path) -> np.ndarray:
    """1 fps greyscale thumbnails of one segment, cached beside it."""
    cached = _signature_path(segment)
    if cached.exists():
        loaded: np.ndarray = np.load(cached)
        return loaded
    # Hardware decode where there is one: thirty cameras' worth of software
    # decode is about two cores, for thumbnails.
    raw = b""
    for hwaccel in (["-hwaccel", "videotoolbox"] if sys.platform == "darwin" else [], []):
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "quiet", "-nostdin", *hwaccel,
            "-i", str(segment),
            "-vf", f"fps=1,scale={SIG_W}:{SIG_H}:flags=area,format=gray",
            "-f", "rawvideo", "-",
        ]  # fmt: skip
        raw = subprocess.run(cmd, capture_output=True, check=False).stdout
        if raw:
            break
    flat = np.frombuffer(raw, dtype=np.uint8)
    frames = flat[: len(flat) // (SIG_W * SIG_H) * SIG_W * SIG_H].reshape(-1, SIG_H, SIG_W)
    np.save(cached, frames)
    return frames


def run_timeline(run: Run) -> tuple[np.ndarray, np.ndarray]:
    """(N, SIG_H*SIG_W) float32 thumbnails indexed by whole second of the run,
    plus a mask of which seconds hold one."""
    if not run.segments:
        return np.zeros((0, SIG_W * SIG_H), np.float32), np.zeros(0, bool)
    length = int(np.ceil(run.span_s)) + 1
    frames = np.zeros((length, SIG_W * SIG_H), np.float32)
    mask = np.zeros(length, bool)
    for seg in run.segments:
        for i, thumb in enumerate(segment_signature(seg.path)):
            t = round(seg.start_s + i)
            if 0 <= t < length:
                frames[t] = thumb.reshape(-1)
                mask[t] = True
    return frames, mask


def _slide(
    ref: np.ndarray, ref_mask: np.ndarray, frames: np.ndarray, mask: np.ndarray, first_k: int
) -> np.ndarray:
    """Mean absolute difference between `ref` and the same-length window of
    `frames` at every start index from `first_k`; inf where either window is
    mostly uncovered."""
    window = len(ref)
    distances = np.full(len(frames), np.inf, np.float32)
    if window == 0 or ref_mask.mean() < 0.9:
        return distances
    for k in range(max(first_k, 0), len(frames) - window + 1):
        both = ref_mask & mask[k : k + window]
        if both.mean() < 0.9:
            continue
        distances[k] = float(np.abs(frames[k : k + window][both] - ref[both]).mean())
    return distances


def _window_distances(
    frames: np.ndarray, mask: np.ndarray, ref_start: int, window: int, min_shift: int
) -> np.ndarray:
    ref = frames[ref_start : ref_start + window]
    ref_mask = mask[ref_start : ref_start + window]
    if len(ref) < window:
        return np.full(len(frames), np.inf, np.float32)
    return _slide(ref, ref_mask, frames, mask, ref_start + min_shift)


def _is_match(distances: np.ndarray) -> int | None:
    """Index of a believable match: far better than a typical shift."""
    finite = distances[np.isfinite(distances)]
    if len(finite) < 30:
        return None
    k = int(np.argmin(distances))
    distance, typical = float(distances[k]), float(np.median(finite))
    if distance > MATCH_MAX_ABS or distance > MATCH_RATIO * typical:
        return None
    return k


def detect_loop(frames: np.ndarray, mask: np.ndarray) -> dict[str, Any] | None:
    """Loop period in seconds within one run, or None if it has not repeated.

    Two reference windows a minute and a half apart must each match far
    better than a typical shift does, and agree on the period — a single
    match is not believed, because a static scene matches everywhere.
    """
    found = []
    for ref_start in (REF_START_S, REF_START_S + REF_WINDOW_S + 30):
        distances = _window_distances(frames, mask, ref_start, REF_WINDOW_S, MIN_PERIOD_S)
        finite = distances[np.isfinite(distances)]
        if len(finite) < 30:
            return None
        k = int(np.argmin(distances))
        distance, typical = float(distances[k]), float(np.median(finite))
        if distance > MATCH_MAX_ABS or distance > MATCH_RATIO * typical:
            return None
        # Every multiple of the period matches equally well; the period is
        # the first of them.
        near_best = np.flatnonzero(distances <= max(distance * 1.5, distance + 0.5))
        first = int(near_best[0])
        cluster_end = first + 1
        while cluster_end in near_best:
            cluster_end += 1
        k = first + int(np.argmin(distances[first:cluster_end]))
        found.append((k - ref_start, float(distances[k]), typical))
    (p1, d1, t1), (p2, _, _) = found
    if abs(p1 - p2) > PERIOD_AGREEMENT_S:
        return None
    return {"period_s": round((p1 + p2) / 2), "distance": round(d1, 2), "typical": round(t1, 2)}


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------


def _free_gb(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free / 1e9


async def _get_catalogue(settings: Any) -> Any:
    """GET the catalogue after the form login it sits behind (see
    sentinel_core.gov_catalogue). Returns the httpx response."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(
            f"{settings.gov_hls_base_url}/auth/login",
            data={
                "email": settings.gov_access_email,
                "password": settings.gov_access_password.get_secret_value(),
            },
        )
        return await client.get(settings.gov_catalogue_url)


async def _fetch_catalogue() -> tuple[list[dict[str, Any]], Any]:
    """The raw catalogue exactly as served, plus the settings that reached it.

    Saved as a snapshot on every successful read; a resumed capture whose
    account is cooling down (the catalogue answers 403 then) falls back to
    that snapshot rather than refusing to start.
    """
    import httpx

    from sentinel_core.config import Settings
    from sentinel_core.gov_catalogue import GovCatalogueClient

    settings = Settings()
    if not settings.gov_access_email:
        raise SystemExit("set SENTINEL_GOV_ACCESS_EMAIL/PASSWORD in .env to capture the grid.")
    try:
        response = await _get_catalogue(settings)
        response.raise_for_status()
        entries = GovCatalogueClient._extract_entries(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        if not RAW_CATALOGUE_PATH.exists():
            raise SystemExit(f"could not read the grid's catalogue: {exc}") from exc
        logger.warning("catalogue unavailable (%s) — using the saved snapshot", exc)
        return json.loads(RAW_CATALOGUE_PATH.read_text())["entries"], settings
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    RAW_CATALOGUE_PATH.write_text(
        json.dumps(
            {"captured_at": datetime.now(UTC).isoformat(), "source": settings.gov_catalogue_url,
             "entries": entries},
            indent=2,
        )
    )  # fmt: skip
    return entries, settings


class QuotaGate:
    """The grid meters watch time per account. Once it runs out, every
    stream is refused (RTSP 401, catalogue 403 "watch time limit reached")
    until a cooldown of unstated length passes — measured at under fifteen
    minutes once (evidence/M14-EVIDENCE-RUN-FINDINGS.md). Cameras wait here
    instead of each retrying against a closed door, and one probe of the
    catalogue decides when it has reopened.
    """

    def __init__(self, settings: Any, probe_interval_s: float) -> None:
        self._settings = settings
        self._interval = probe_interval_s
        self._open = asyncio.Event()
        self._open.set()
        self._probe: asyncio.Task[None] | None = None

    def trip(self) -> None:
        if not self._open.is_set():
            return
        self._open.clear()
        logger.warning("watch-time quota reached — pausing every camera until it clears")
        self._probe = asyncio.create_task(self._wait_for_cooldown())

    async def wait(self, stop: asyncio.Event) -> None:
        waiters = [asyncio.create_task(self._open.wait()), asyncio.create_task(stop.wait())]
        _, pending = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()

    async def _wait_for_cooldown(self) -> None:
        import httpx

        paused = time.time()
        while True:
            await asyncio.sleep(self._interval)
            try:
                status = (await _get_catalogue(self._settings)).status_code
            except httpx.HTTPError as exc:
                logger.info("quota probe failed (%s); still paused", type(exc).__name__)
                continue
            if status == 200:
                logger.info("quota cleared after %.0f min — resuming", (time.time() - paused) / 60)
                self._open.set()
                return
            logger.info("still cooling down (catalogue HTTP %d)", status)


def _redact(text: str, settings: Any) -> str:
    from urllib.parse import quote

    secret = settings.gov_access_password.get_secret_value()
    for value in (secret, quote(secret, safe=""), settings.gov_access_email,
                  quote(settings.gov_access_email, safe="")):  # fmt: skip
        if value:
            text = text.replace(value, "***")
    return text


class CameraCapture:
    """Records one camera until it has --max-minutes of footage (or its clip
    visibly repeats within one connection), reconnecting as needed."""

    def __init__(
        self, camera_id: str, url: str, settings: Any, args: argparse.Namespace, quota: QuotaGate
    ) -> None:
        self.camera_id = camera_id
        self.quota = quota
        self.url = url
        self.settings = settings
        self.args = args
        self.dir = _camera_dir(camera_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.loop: dict[str, Any] | None = None
        self.state_path = self.dir / "state.json"
        state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self.loop = state.get("loop")
        self.reason: str | None = state.get("stopped")

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps({"loop": self.loop, "stopped": self.reason}))

    def recorded_s(self) -> float:
        return sum(run.span_s for run in camera_runs(self.camera_id))

    def _done(self) -> str | None:
        # A stored "max-duration" is re-judged against this run's
        # --max-minutes, so resuming with a bigger budget records more.
        if self.reason == "loop":
            return self.reason
        if self.loop is not None:
            run = next(r for r in camera_runs(self.camera_id) if r.run_id == self.loop["run_id"])
            if run.span_s >= self.loop["period_s"] + REF_START_S + REF_WINDOW_S + LOOP_MARGIN_S:
                return "loop"
        if self.recorded_s() >= self.args.max_minutes * 60:
            return "max-duration"
        if _free_gb(MIRROR_DIR) < self.args.min_free_gb:
            return "disk"
        return None

    async def scan(self, runs: list[Run]) -> None:
        """Look for the loop in each given run, keeping the first found."""
        for run in runs:
            if self.loop is not None:
                return
            if run.span_s < REF_START_S + 2 * REF_WINDOW_S + 30 + MIN_PERIOD_S:
                continue
            frames, mask = await asyncio.to_thread(run_timeline, run)
            loop = await asyncio.to_thread(detect_loop, frames, mask)
            if loop:
                self.loop = {"run_id": run.run_id, **loop}
                logger.info("%s: loop found — %s", self.camera_id, self.loop)
                self._save_state()

    async def run(self, stop: asyncio.Event) -> None:
        await self.scan(camera_runs(self.camera_id))  # anything recorded before a resume
        backoff = 2.0
        while not stop.is_set():
            reason = self._done()
            if reason:
                self.reason = reason
                self._save_state()
                logger.info("%s: done (%s)", self.camera_id, reason)
                return
            await self.quota.wait(stop)
            if stop.is_set():
                return
            run_id = f"run{int(time.time())}"
            started = time.time()
            with (self.dir / "runs.jsonl").open("a") as runs:
                runs.write(json.dumps({"id": run_id, "started": started}) + "\n")
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-rtsp_transport", "tcp", "-timeout", "15000000",
                "-i", self.url,
                "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
                "-f", "segment", "-segment_time", str(SEGMENT_S),
                "-segment_format", "mpegts", "-reset_timestamps", "1",
                "-segment_list", str(self.dir / f"{run_id}.csv"),
                "-segment_list_type", "csv",
                str(self.dir / f"{run_id}-%05d.ts"),
            ]  # fmt: skip
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
            )
            watcher = asyncio.create_task(self._watch(proc, stop))
            _, stderr = await proc.communicate()
            watcher.cancel()
            lived = time.time() - started
            if stop.is_set() or self._done():
                continue
            await self.scan(camera_runs(self.camera_id)[-1:])
            error = _redact(stderr.decode(errors="replace").strip()[-200:], self.settings)
            if "401 Unauthorized" in error or "403 Forbidden" in error:
                self.quota.trip()
                continue
            logger.warning(
                "%s: stream ended after %.0fs (exit %s) %s",
                self.camera_id,
                lived,
                proc.returncode,
                error,
            )
            # A connection that delivered footage before the grid dropped it
            # is not a failed dial; only repeated failures back off.
            backoff = 2.0 if lived > 10 else min(backoff * 2, 30.0)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), backoff)

    async def _watch(self, proc: asyncio.subprocess.Process, stop: asyncio.Event) -> None:
        """Re-check the loop as segments close; end the recording once done."""
        while proc.returncode is None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self.args.check_interval)
            if not stop.is_set():
                runs = camera_runs(self.camera_id)
                await self.scan(runs[-1:])
                if not self._done():
                    continue
            # Stop cleanly: SIGINT lets the segment muxer close its last file.
            if proc.returncode is None:
                proc.send_signal(signal.SIGINT)
            return


async def capture(args: argparse.Namespace) -> None:
    entries, settings = await _fetch_catalogue()
    ids = [str(e.get("id") or e.get("camera_id")) for e in entries]
    if args.cameras:
        wanted = set(args.cameras.split(","))
        ids = [i for i in ids if i in wanted]
    logger.info("capturing %d camera(s) into %s", len(ids), RAW_DIR)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    quota = QuotaGate(settings, args.quota_probe_interval)
    captures = [
        CameraCapture(i, settings.gov_stream_url("rtsp", i), settings, args, quota) for i in ids
    ]
    # Watch time is metered per account, so concurrency does not change how
    # much footage one quota buys. It decides what that footage is: a few
    # cameras recorded at length, or every camera's first minutes over and
    # over, since a replay restarts from the top after each cooldown.
    slots = asyncio.Semaphore(args.concurrency)

    async def take_turn(camera: CameraCapture) -> None:
        async with slots:
            if not stop.is_set():
                await camera.run(stop)

    reporter = asyncio.create_task(_report_progress(captures, stop))
    await asyncio.gather(*(take_turn(c) for c in captures))
    reporter.cancel()
    _print_capture_summary(captures)


async def _report_progress(captures: list[CameraCapture], stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.sleep(300)
        looped = sum(1 for c in captures if c.loop)
        done = sum(1 for c in captures if c.reason)
        logger.info(
            "progress: %d/%d looped, %d/%d finished, %.1f GB free",
            looped, len(captures), done, len(captures), _free_gb(MIRROR_DIR),
        )  # fmt: skip


def _print_capture_summary(captures: list[CameraCapture]) -> None:
    for c in captures:
        period = c.loop["period_s"] if c.loop else None
        print(
            f"  {c.camera_id:8s} recorded {c.recorded_s() / 60:6.1f} min  "
            f"loop {f'{period / 60:.1f} min' if period else 'not found':>10s}  "
            f"({c.reason or 'interrupted'})"
        )


# --------------------------------------------------------------------------
# assemble: stitch each camera's footage into one pass of its clip
# --------------------------------------------------------------------------
#
# What we record is not one clean pass of each clip. The grid drops
# connections every minute or two, its quota pauses everything for a
# cooldown, and a camera's replay starts again from the top of its clip
# whenever it has had no viewer for a few seconds — so footage recorded after
# a long pause usually repeats the start of what we already have.
#
# So footage is laid out by what it shows rather than when it was recorded.
# Runs that reconnected within a few seconds are one *chain*: the replay
# kept going, and wall-clock gaps place them. Chains are merged where their
# footage matches — filling each other's reconnect gaps or extending each
# other — into *sections*, each a continuous stretch of the clip held once.
# A chain that matches nothing recorded so far is footage from elsewhere in
# the clip (the grid's timeline moved on while we were paused), so it starts
# a section of its own rather than being thrown away. Sections are played in
# the order they were recorded, with a scene cut between them — the same
# kind of cut the remote makes at its own loop point.

# The first seconds of a connection are the gateway's buffered GOP replayed
# faster than real time, and may start mid-GOP.
JOIN_SKIP_S = 2.0
# A reconnect this quick finds the camera's replay still running.
CHAIN_GAP_S = 8.0
# Overlaps shorter than this are not worth a cut.
MIN_PIECE_S = 1.0


@dataclass(frozen=True, slots=True)
class Piece:
    """Part of one recorded segment, placed on its camera's clip axis."""

    segment: Segment
    position_s: float  # clip position of the segment's first frame
    inpoint_s: float  # within the segment
    outpoint_s: float

    @property
    def start(self) -> float:
        return self.position_s + self.inpoint_s

    @property
    def end(self) -> float:
        return self.position_s + self.outpoint_s

    def shifted(self, by: float) -> Piece:
        return Piece(self.segment, self.position_s + by, self.inpoint_s, self.outpoint_s)


def camera_chains(camera_id: str) -> list[tuple[float, list[Piece]]]:
    """Runs grouped into stretches of uninterrupted replay: (wall-clock time
    the chain began, its pieces on its own axis with 0 = that moment)."""
    chains: list[tuple[float, list[Piece]]] = []
    origin = previous_end = 0.0
    for run in sorted(camera_runs(camera_id), key=lambda r: r.started):
        # A segment with no decodable frame (a connection that died before
        # its first keyframe) has nothing to contribute.
        segments = [seg for seg in run.segments if len(segment_signature(seg.path))]
        if not segments:
            continue
        if not chains or run.started - previous_end > CHAIN_GAP_S:
            origin = run.started
            chains.append((origin, []))
        for i, seg in enumerate(segments):
            skip = JOIN_SKIP_S if i == 0 else 0.0
            if seg.duration_s > skip + MIN_PIECE_S:
                chains[-1][1].append(
                    Piece(seg, run.started - origin + seg.start_s, skip, seg.duration_s)
                )
        previous_end = run.started + run.span_s
    return [(start, pieces) for start, pieces in chains if pieces]


def _covered_s(pieces: list[Piece]) -> float:
    return sum(p.end - p.start for p in pieces)


def match_offset(base: list[Piece], other: list[Piece]) -> float | None:
    """Shift that lines `other` up with `base`, or None if they share no
    recognisable footage. Tries `other`'s opening minute inside `base`, then
    `base`'s opening minute inside `other` (for a chain that began earlier
    in the clip than the base did)."""
    base_frames, base_mask, base_origin = clip_timeline(base)
    other_frames, other_mask, other_origin = clip_timeline(other)
    window = slice(REF_START_S, REF_START_S + REF_WINDOW_S)
    k = _is_match(_slide(other_frames[window], other_mask[window], base_frames, base_mask, 0))
    if k is not None:
        return (base_origin + k) - (other_origin + REF_START_S)
    k = _is_match(_slide(base_frames[window], base_mask[window], other_frames, other_mask, 0))
    if k is not None:
        return (base_origin + REF_START_S) - (other_origin + k)
    return None


def _merge(section: list[Piece], chain: list[Piece], offset: float) -> None:
    """Add the parts of `chain` (shifted onto the section's axis) that the
    section does not already hold."""
    covered = [(p.start, p.end) for p in section]
    for piece in (p.shifted(offset) for p in chain):
        for start, end in _uncovered(piece.start, piece.end, covered):
            if end - start >= MIN_PIECE_S:
                section.append(
                    Piece(piece.segment, piece.position_s, start - piece.position_s,
                          end - piece.position_s)
                )  # fmt: skip
                covered.append((start, end))


def place_camera(camera_id: str) -> list[list[Piece]]:
    """Every recorded moment of a camera, each once, as sections of the clip
    in the order they were recorded; each section's pieces in clip order."""
    chains = camera_chains(camera_id)
    # Longest first, so short reconnect fragments merge into a long stretch
    # rather than seeding sections of their own.
    sections: list[tuple[float, list[Piece]]] = []
    for began, chain in sorted(chains, key=lambda c: _covered_s(c[1]), reverse=True):
        for i, (first_seen, section) in enumerate(sections):
            offset = match_offset(section, chain)
            if offset is not None:
                _merge(section, chain, offset)
                sections[i] = (min(first_seen, began), section)
                break
        else:
            sections.append((began, list(chain)))
    return [sorted(section, key=lambda p: p.start) for _, section in sorted(sections)]


def _first_start(camera_id: str) -> float:
    return min(r.started for r in camera_runs(camera_id))


def _uncovered(
    start: float, end: float, covered: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    gaps = [(start, end)]
    for c_start, c_end in covered:
        next_gaps = []
        for g_start, g_end in gaps:
            if c_end <= g_start or c_start >= g_end:
                next_gaps.append((g_start, g_end))
                continue
            if g_start < c_start:
                next_gaps.append((g_start, c_start))
            if c_end < g_end:
                next_gaps.append((c_end, g_end))
        gaps = next_gaps
    return gaps


def clip_timeline(pieces: list[Piece]) -> tuple[np.ndarray, np.ndarray, int]:
    """Thumbnails on the clip axis (one per second), mask, and the axis origin."""
    if not pieces:
        return np.zeros((0, SIG_W * SIG_H), np.float32), np.zeros(0, bool), 0
    origin = int(np.floor(pieces[0].start))
    length = int(np.ceil(max(p.end for p in pieces))) - origin + 1
    frames = np.zeros((length, SIG_W * SIG_H), np.float32)
    mask = np.zeros(length, bool)
    for piece in pieces:
        for i, thumb in enumerate(segment_signature(piece.segment.path)):
            if piece.inpoint_s <= i < piece.outpoint_s:
                t = round(piece.position_s + i) - origin
                if 0 <= t < length:
                    frames[t] = thumb.reshape(-1)
                    mask[t] = True
    return frames, mask, origin


def trim_to_loop(pieces: list[Piece], period: float) -> list[Piece]:
    """Keep the first `period` seconds of the clip axis."""
    if not pieces:
        return pieces
    end = pieces[0].start + period
    kept = []
    for piece in pieces:
        if piece.start >= end:
            break
        out = min(piece.outpoint_s, end - piece.position_s)
        if out - piece.inpoint_s >= MIN_PIECE_S:
            kept.append(Piece(piece.segment, piece.position_s, piece.inpoint_s, out))
    return kept


def _probe(path: Path, entries: str) -> dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
        capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    parsed: dict[str, Any] = json.loads(out or "{}")
    return parsed


def _frame_gaps(path: Path, fps: float) -> dict[str, float]:
    """How much of the clip the remote failed to deliver: frame intervals
    more than three nominal frames long. Read from packet timestamps — no
    decode needed."""
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    times = sorted(
        float(v) for v in (ln.strip().strip(",") for ln in out.splitlines()) if v not in ("", "N/A")
    )
    deltas = np.diff(np.asarray(times)) if len(times) > 1 else np.zeros(0)
    limit = 3.0 / fps if fps else 0.5
    missing = float(deltas[deltas > limit].sum()) if len(deltas) else 0.0
    span = float(times[-1] - times[0]) if len(times) > 1 else 0.0
    return {
        "gaps": int((deltas > limit).sum()),
        "missing_s": round(missing, 1),
        "missing_pct": round(100 * missing / span, 2) if span else 0.0,
    }


# Boxes on the way from the top of an MP4 to an H.265 track's hvcC, with the
# bytes each carries before its child boxes.
_HVCC_PATH_HEADERS = {
    b"moov": 0, b"trak": 0, b"mdia": 0, b"minf": 0, b"stbl": 0,
    b"stsd": 8, b"hvc1": 78, b"hev1": 78,
}  # fmt: skip


def _dedupe_hvcc(path: Path) -> None:
    """Drop repeated parameter sets from an H.265 track's hvcC, in place.

    Some grid cameras send every VPS/SPS/PPS twice before each keyframe, so
    the copy's decoder configuration lists each one twice, ffmpeg advertises
    `sprop-vps=X,X` when publishing it, and MediaMTX refuses the stream
    ("invalid sprop-vps"). Re-encoding would fix that by changing the
    footage; this fixes only the metadata. The file must have its moov after
    the media (no faststart), so resizing it moves no sample offsets.
    """
    data = bytearray(path.read_bytes())

    def boxes(start: int, end: int) -> list[tuple[int, int, bytes]]:
        found, at = [], start
        while at + 8 <= end:
            size = int.from_bytes(data[at : at + 4], "big")
            if size < 8:
                break
            found.append((at, size, bytes(data[at + 4 : at + 8])))
            at += size
        return found

    def find(start: int, end: int, chain: list[int]) -> tuple[int, list[int]] | None:
        for at, size, kind in boxes(start, end):
            if kind == b"hvcC":
                return at, chain
            if kind in _HVCC_PATH_HEADERS:
                hit = find(at + 8 + _HVCC_PATH_HEADERS[kind], at + size, [*chain, at])
                if hit:
                    return hit
        return None

    hit = find(0, len(data), [])
    if hit is None:
        return
    at, ancestors = hit
    size = int.from_bytes(data[at : at + 4], "big")
    body = data[at + 8 : at + size]
    out, cursor = bytearray(body[:22]), 23
    out.append(body[22])  # numOfArrays
    for _ in range(body[22]):
        kind, count = body[cursor], int.from_bytes(body[cursor + 1 : cursor + 3], "big")
        cursor += 3
        units: list[bytes] = []
        for _ in range(count):
            length = int.from_bytes(body[cursor : cursor + 2], "big")
            unit = bytes(body[cursor + 2 : cursor + 2 + length])
            cursor += 2 + length
            if unit not in units:
                units.append(unit)
        out += bytes([kind]) + len(units).to_bytes(2, "big")
        for unit in units:
            out += len(unit).to_bytes(2, "big") + unit
    delta = len(out) - len(body)
    if delta == 0:
        return
    for box in ancestors:
        new_size = int.from_bytes(data[box : box + 4], "big") + delta
        data[box : box + 4] = new_size.to_bytes(4, "big")
    data[at : at + size] = (size + delta).to_bytes(4, "big") + b"hvcC" + out
    path.write_bytes(bytes(data))


def _concat_list(pieces: list[Piece], sources: dict[Path, Path]) -> str:
    """A concat-demuxer script playing the pieces in clip order.

    `sources` maps each raw segment to the MP4 remux actually read. In/out
    points are absolute timestamps inside each file, so each file's own
    start time is added.
    """
    lines = ["ffconcat version 1.0"]
    offsets: dict[Path, float] = {}
    for piece in pieces:
        path = sources[piece.segment.path]
        if path not in offsets:
            fmt = _probe(path, "format=start_time").get("format", {})
            offsets[path] = float(fmt.get("start_time", 0) or 0)
        lines.append(f"file '{path.as_posix()}'")
        if piece.inpoint_s > 0.05:
            lines.append(f"inpoint {offsets[path] + piece.inpoint_s:.3f}")
        if piece.outpoint_s < piece.segment.duration_s - 0.05:
            lines.append(f"outpoint {offsets[path] + piece.outpoint_s:.3f}")
    return "\n".join(lines) + "\n"


def assemble_camera(camera_id: str) -> dict[str, Any]:
    """Stitch one pass of a camera's clip into clips/<id>.mp4."""
    sections = place_camera(camera_id)
    if sum(_covered_s(section) for section in sections) < 30:
        return {"camera_id": camera_id, "error": "under 30 s recorded"}
    loop = None
    for i, section in enumerate(sections):
        frames, mask, _ = clip_timeline(section)
        found = detect_loop(frames, mask)
        if found:
            # This stretch repeated within itself: keep one pass of it.
            sections[i] = trim_to_loop(section, found["period_s"])
            loop = loop or found
    pieces = [piece for section in sections for piece in section]

    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    clip = CLIPS_DIR / f"{camera_id}.mp4"
    first = pieces[0].segment.path
    codec = _probe(first, "stream=codec_name").get("streams", [{}])[0].get("codec_name")
    # hvc1 is the H.265 tag every mp4 player (and MediaMTX's demuxer) accepts.
    tag = ["-tag:v", "hvc1"] if codec == "hevc" else []
    with tempfile.TemporaryDirectory(dir=CLIPS_DIR) as scratch:
        # Seeking to an in-point inside raw MPEG-TS is unreliable — one
        # segment whose timestamps started late contributed nothing at all —
        # so each segment is first remuxed (stream copy) to an indexed MP4.
        sources: dict[Path, Path] = {}
        for segment in dict.fromkeys(piece.segment.path for piece in pieces):
            remuxed = Path(scratch) / f"{segment.stem}.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "quiet", "-nostdin",
                 "-i", str(segment), "-map", "0:v:0", "-map", "0:a?", "-c", "copy", *tag,
                 str(remuxed)],
                check=False,
            )  # fmt: skip
            sources[segment] = remuxed
        pieces = [p for p in pieces if sources[p.segment.path].exists()]
        listing = Path(scratch) / "clip.ffconcat"
        listing.write_text(_concat_list(pieces, sources))
        stitched = Path(scratch) / "stitched.mp4"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-map", "0:v:0", "-map", "0:a?", "-c", "copy", *tag,
            "-avoid_negative_ts", "make_zero", str(stitched),
        ]  # fmt: skip
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and codec == "hevc":
            _dedupe_hvcc(stitched)
        if result.returncode == 0:
            result = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
                 "-i", str(stitched), "-map", "0", "-c", "copy", "-movflags", "+faststart",
                 str(clip)],
                capture_output=True, text=True, check=False,
            )  # fmt: skip
    info = _probe(
        clip, "stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration,size"
    )
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if result.returncode != 0 or video is None:
        clip.unlink(missing_ok=True)
        return {"camera_id": camera_id, "error": result.stderr.strip()[-300:] or "no video"}
    num, _, den = str(video.get("avg_frame_rate", "0/1")).partition("/")
    fps = float(num) / float(den) if float(den or 0) else 0.0
    kept = {id(p) for p in pieces}
    sections = [[p for p in section if id(p) in kept] for section in sections]
    sections = [section for section in sections if section]
    return {
        "camera_id": camera_id,
        "clip": clip.relative_to(MIRROR_DIR).as_posix(),
        "codec": {"hevc": "h265"}.get(video["codec_name"], video["codec_name"]),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": round(fps, 2),
        "duration_s": round(float(info["format"]["duration"]), 1),
        "size_mb": round(int(info["format"]["size"]) / 1e6, 1),
        "loop_s": loop["period_s"] if loop else None,
        # Continuous stretches of the remote's clip, in playback order: how
        # long each spans, and how much of that span was actually delivered.
        "sections": [
            {
                "span_s": round(section[-1].end - section[0].start, 1),
                "held_pct": round(
                    100 * _covered_s(section) / max(section[-1].end - section[0].start, 1e-6), 1
                ),
            }
            for section in sections
        ],
        "recorded_from": datetime.fromtimestamp(_first_start(camera_id), UTC).isoformat(),
        "delivery": _frame_gaps(clip, fps),
    }


def write_catalogue(raw_entries: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> int:
    """The mirror's camera list, in CameraDescriptor shape.

    Names, ids and (geocoded) locations come from the snapshot of the real
    catalogue through the same parser the live grid uses, so a mirrored
    camera looks exactly like its original — only the stream URL differs.
    """
    from pydantic import SecretStr

    from sentinel_core.config import Settings
    from sentinel_core.gov_catalogue import _parse_entry
    from sentinel_core.schemas import CameraDescriptor, StreamProfile, StreamProtocol

    # Blank credentials: the parser builds remote URLs that are discarded
    # below, and they must not carry the real login into this file.
    settings = Settings(gov_access_email="", gov_access_password=SecretStr(""))
    clips = {m["camera_id"]: m for m in manifest if "clip" in m}
    descriptors = []
    for raw in raw_entries:
        parsed = _parse_entry(raw, settings)
        clip = clips.get(parsed.camera_id)
        if clip is None:
            continue
        descriptor = CameraDescriptor.model_validate(
            {
                **parsed.model_dump(exclude={"profiles", "attributes", "status"}),
                "profiles": [
                    StreamProfile(
                        protocol=StreamProtocol.RTSP,
                        url=mirror_rtsp_url(parsed.camera_id),
                        codec=clip["codec"],
                        width=clip["width"],
                        height=clip["height"],
                        declared_fps=clip["fps"] or None,
                    )
                ],
                "attributes": {
                    "source": "gov_mirror",
                    "sections": str(len(clip.get("sections", [])) or 1),
                    "recorded_from": clip["recorded_from"],
                },
            }
        )
        descriptors.append(descriptor.model_dump(mode="json"))
    CATALOGUE_PATH.write_text(json.dumps(descriptors, indent=2))
    return len(descriptors)


def assemble(args: argparse.Namespace) -> None:
    if not RAW_CATALOGUE_PATH.exists():
        raise SystemExit(f"no catalogue snapshot at {RAW_CATALOGUE_PATH} — run `capture` first.")
    raw_entries: list[dict[str, Any]] = json.loads(RAW_CATALOGUE_PATH.read_text())["entries"]
    ids = [str(e.get("id") or e.get("camera_id")) for e in raw_entries]
    recorded = [i for i in ids if camera_runs(i)]
    if args.cameras:
        wanted = set(args.cameras.split(","))
        recorded = [i for i in recorded if i in wanted]
    previous = {m["camera_id"]: m for m in _load_manifest()}
    for camera_id in recorded:
        record = assemble_camera(camera_id)
        previous[camera_id] = record
        if "error" in record:
            print(f"  {camera_id:8s} skipped: {record['error']}")
            continue
        loop = f"loops at {record['loop_s'] / 60:.1f} min" if record["loop_s"] else ""
        print(
            f"  {camera_id:8s} {record['duration_s'] / 60:5.1f} min "
            f"in {len(record['sections'])} section(s), {record['codec']} "
            f"{record['width']}x{record['height']}@{record['fps']} {record['size_mb']} MB "
            f"missing {record['delivery']['missing_pct']}% {loop}"
        )
        if args.prune_raw:
            shutil.rmtree(_camera_dir(camera_id))
    manifest = [previous[i] for i in sorted(previous)]
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    count = write_catalogue(raw_entries, manifest)
    print(f"catalogue written to {CATALOGUE_PATH} ({count} cameras)")


def _load_manifest() -> list[dict[str, Any]]:
    return json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else []


# --------------------------------------------------------------------------
# start / stop / status: replay the mirror into the local relay
# --------------------------------------------------------------------------


def mirror_path(camera_id: str) -> str:
    return f"{MIRROR_PATH_PREFIX}/{camera_id}"


def mirror_rtsp_url(camera_id: str) -> str:
    """What consumers read — anonymous, like every other relay path."""
    return f"rtsp://{RELAY_RTSP_HOST}:{RELAY_RTSP_PORT}/{mirror_path(camera_id)}"


def _publish_url(camera_id: str) -> str:
    return (
        f"rtsp://{RELAY_PUBLISH_USER}:{RELAY_PUBLISH_PASS}@"
        f"{RELAY_RTSP_HOST}:{RELAY_RTSP_PORT}/{mirror_path(camera_id)}"
    )


def start(args: argparse.Namespace) -> None:
    clips = [m for m in _load_manifest() if "clip" in m]
    if args.cameras:
        wanted = set(args.cameras.split(","))
        clips = [m for m in clips if m["camera_id"] in wanted]
    if not clips:
        raise SystemExit("no assembled clips — run `capture` then `assemble` first.")
    stop()
    pids: dict[str, int] = {}
    for record in clips:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin",
            "-re", "-stream_loop", "-1",
            "-i", str(MIRROR_DIR / record["clip"]),
            "-map", "0", "-c", "copy",
            "-rtsp_transport", "tcp",
            "-f", "rtsp", _publish_url(record["camera_id"]),
        ]  # fmt: skip
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
        pids[record["camera_id"]] = proc.pid
        print(f"publish {record['camera_id']} -> {mirror_rtsp_url(record['camera_id'])}")
    PIDS_PATH.write_text(json.dumps(pids, indent=2))
    time.sleep(3)
    status()


def stop() -> None:
    if not PIDS_PATH.exists():
        return
    for camera_id, pid in json.loads(PIDS_PATH.read_text()).items():
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"stopped {camera_id} (pid {pid})")
        except ProcessLookupError:
            pass
    PIDS_PATH.unlink(missing_ok=True)


def status() -> None:
    import httpx

    try:
        response = httpx.get(f"{RELAY_API_URL}/v3/paths/list", timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SystemExit(f"could not reach the relay API ({exc}) — is `make up` running?") from exc
    live = {item["name"]: item for item in response.json()["items"]}
    for record in _load_manifest():
        if "clip" not in record:
            continue
        path = mirror_path(record["camera_id"])
        item = live.get(path)
        marker = "\u2713 live" if item and item.get("ready") else "\u2717 not publishing"
        print(f"  {record['camera_id']:8s} {path:16s} {marker}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="record every camera's stream to disk")
    cap.add_argument("--cameras", help="comma-separated ids (default: the whole catalogue)")
    cap.add_argument(
        "--max-minutes", type=float, default=15,
        help="footage to record per camera (default 15)",
    )  # fmt: skip
    cap.add_argument(
        "--min-free-gb", type=float, default=6.0,
        help="stop recording when free disk drops below this (default 6)",
    )  # fmt: skip
    cap.add_argument(
        "--concurrency", type=int, default=6,
        help="cameras recorded at once (default 6 — few enough that each gets long "
        "unbroken stretches before the quota runs out)",
    )  # fmt: skip
    cap.add_argument(
        "--quota-probe-interval", type=float, default=120.0,
        help="seconds between checks for the end of a watch-time cooldown (default 120)",
    )  # fmt: skip
    cap.add_argument("--check-interval", type=float, default=120.0, help=argparse.SUPPRESS)

    asm = sub.add_parser("assemble", help="cut one loop per camera and write the catalogue")
    asm.add_argument("--cameras", help="comma-separated ids (default: everything recorded)")
    asm.add_argument(
        "--prune-raw", action="store_true",
        help="delete each camera's raw recording once its clip is written",
    )  # fmt: skip
    pub = sub.add_parser("start", help="loop-publish the clips into the local relay")
    pub.add_argument("--cameras", help="comma-separated ids (default: every assembled clip)")
    sub.add_parser("stop", help="stop the publishers")
    sub.add_parser("status", help="show which mirror/* paths the relay sees")

    args = parser.parse_args()
    if args.command in ("capture", "assemble", "start") and shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found on PATH (e.g. `brew install ffmpeg`).")
    if args.command == "capture":
        asyncio.run(capture(args))
    elif args.command == "assemble":
        assemble(args)
    elif args.command == "start":
        start(args)
    elif args.command == "stop":
        stop()
    elif args.command == "status":
        status()


if __name__ == "__main__":
    main()
