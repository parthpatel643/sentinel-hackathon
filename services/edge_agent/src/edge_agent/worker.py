"""Live edge worker: the process that actually ties capture, ANPR and the
API together, rather than each being proven only in isolation (unit tests
with fake ports) or via manual curl (M4/M5 verification).

Per camera: `CameraSupervisor` owns reconnect/backoff, `AnprPipeline` turns
frames into resolved-plate events, and this module posts each event to
`POST /api/v1/detections` and periodically PATCHes camera health. Detector
and OCR models are loaded once and shared across every camera's pipeline —
they are stateless inference engines; only the tracker/voter state in each
`AnprPipeline` instance is per-camera.

Three camera sources, selected with `--source`:

- `synthetic` (default): the M1 local RTSP grid
  (`scripts/synthetic_grid.py`) — 8 cameras, unlimited concurrency, no
  external network dependency.
- `gov`: the real Sentinel Camera Grid (the organisers' actual integration
  target), fetched live via `GovCatalogueClient` — 30 cameras as of this
  writing. The integrator guide explicitly asks integrators to "pace your
  load" and open only the cameras being processed, so this defaults to a
  small `--limit` rather than opening all 30 RTSP connections at once.
- `registry`: whatever the core API's camera registry holds — every camera
  onboarded by the wizard, bulk CSV, device discovery or a catalogue sync,
  from any department or vendor. This is the source for real deployments
  (and the Phase-2 finale): the registry is re-read every
  `--resync-interval` seconds, so a camera onboarded while the worker runs
  starts being analysed within one interval, a corrected stream URL replaces
  the old one, and a removed camera is stopped. Cameras on the
  `d_registry_only` tier are metadata-only and never opened.

Usage (with the docker-compose stack and core_api already running — see
README/docs/05-DELIVERY-PLAN.md):

    uv run --package edge-agent python -m edge_agent.worker
    uv run --package edge-agent python -m edge_agent.worker --source gov --limit 4
    uv run --package edge-agent python -m edge_agent.worker --source gov --cameras cam01,cam04
    uv run --package edge-agent python -m edge_agent.worker --source registry --frame-stride 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
import numpy as np

from edge_agent.analytics.frame_clock import FrameClockReader
from edge_agent.analytics.pipeline import AnprPipeline
from edge_agent.analytics.plate_reader import FastAlprPlateReader
from edge_agent.analytics.scheduler import AnalysisScheduler, SchedulerConfig
from edge_agent.analytics.snapshot_writer import SnapshotWriter
from edge_agent.analytics.tamper import TamperDetector
from edge_agent.analytics.vehicle_detector import VehicleDetector
from edge_agent.analytics.zone_rules import Zone, ZoneRuleEngine
from edge_agent.fleet import CameraFleet
from edge_agent.outbox import DetectionOutbox
from edge_agent.pipeline.capture import CaptureConfig
from edge_agent.pipeline.supervisor import CameraSupervisor
from sentinel_core.clock import Frame, FrameTiming
from sentinel_core.config import Settings, get_settings
from sentinel_core.gov_catalogue import GovCatalogueClient
from sentinel_core.relay import (
    ensure_relay_path,
    is_relay_hosted,
    relay_path_for,
    relay_rtsp_url,
    release_relay_path,
)
from sentinel_core.schemas import (
    AnalyticsTier,
    AnprPayload,
    CameraDescriptor,
    CameraStatus,
    Event,
    GeoPoint,
    StreamProfile,
    StreamProtocol,
)

logger = logging.getLogger("edge_agent.worker")

# Relay paths this process pinned open (`sourceOnDemand: false`) and is
# therefore responsible for handing back when it exits.
_WARMED_RELAY_PATHS: set[str] = set()

REPO_ROOT = Path(__file__).resolve().parents[4]
SYNTHETIC_CATALOGUE = REPO_ROOT / "var" / "synthetic-grid" / "catalogue.json"
VEHICLE_MODEL = REPO_ROOT / "models" / "weights" / "yolo11n.onnx"
MODEL_VERSIONS = {
    "vehicle_det": "yolo11n@ultralytics-8.4.158",
    "plate_det": "yolo-v9-t-640@open-image-models-0.6.0",
    "ocr": "cct-xs-v2-global@fast-plate-ocr-1.1.0",
}
HEALTH_REPORT_INTERVAL_S = 5.0
DEFAULT_GOV_LIMIT = 4
DEFAULT_RESYNC_INTERVAL_S = 30.0


def _load_synthetic_descriptors() -> list[CameraDescriptor]:
    if not SYNTHETIC_CATALOGUE.exists():
        raise SystemExit(
            f"no catalogue at {SYNTHETIC_CATALOGUE}. Run:\n"
            "    uv run python scripts/synthetic_grid.py generate\n"
            "    uv run python scripts/synthetic_grid.py start"
        )
    raw: list[dict[str, Any]] = json.loads(SYNTHETIC_CATALOGUE.read_text())
    return [CameraDescriptor.model_validate(entry) for entry in raw]


def _descriptor_from_registry(raw: dict[str, Any]) -> CameraDescriptor | None:
    """A registry camera (the `/api/v1/edge/cameras` shape) as something this
    worker can open, or None when there is nothing to analyse: no RTSP or HLS
    profile, or a camera deliberately kept metadata-only."""
    try:
        tier = AnalyticsTier(raw.get("tier") or AnalyticsTier.B_SAMPLED)
    except ValueError:
        tier = AnalyticsTier.B_SAMPLED
    if tier is AnalyticsTier.D_REGISTRY_ONLY:
        return None
    profiles = []
    for profile in raw.get("profiles") or []:
        try:
            protocol = StreamProtocol(str(profile.get("protocol", "")).lower())
        except ValueError:
            continue
        profiles.append(
            StreamProfile(
                protocol=protocol,
                url=profile["url"],
                codec=profile.get("codec"),
                width=profile.get("width"),
                height=profile.get("height"),
                declared_fps=profile.get("declared_fps"),
            )
        )
    if not any(p.protocol in (StreamProtocol.RTSP, StreamProtocol.HLS) for p in profiles):
        return None
    location = raw.get("location")
    return CameraDescriptor(
        camera_id=raw["camera_id"],
        name=raw.get("name") or raw["camera_id"],
        driver_id=raw.get("driver_id") or "rtsp",
        department=raw.get("department_name"),
        site=raw.get("site_name"),
        location=GeoPoint(lat=location["lat"], lon=location["lon"]) if location else None,
        profiles=profiles,
        tier=tier,
        status=CameraStatus.UNKNOWN,
        attributes=raw.get("attributes") or {},
    )


async def _fetch_registry_descriptors(client: httpx.AsyncClient) -> list[CameraDescriptor]:
    response = await client.get("/api/v1/edge/cameras")
    response.raise_for_status()
    descriptors = [_descriptor_from_registry(raw) for raw in response.json()]
    return [d for d in descriptors if d is not None]


def _select_cameras(
    descriptors: list[CameraDescriptor],
    *,
    cameras: str | None,
    limit: int | None,
    department: str | None = None,
    warn_missing: bool = True,
) -> list[CameraDescriptor]:
    if department:
        wanted_department = department.casefold()
        descriptors = [
            d for d in descriptors if (d.department or "").casefold() == wanted_department
        ]
    if cameras:
        wanted = set(cameras.split(","))
        descriptors = [d for d in descriptors if d.camera_id in wanted]
        missing = wanted - {d.camera_id for d in descriptors}
        if missing and warn_missing:
            logger.warning("requested camera ids not found in the catalogue: %s", sorted(missing))
        return descriptors
    return descriptors[:limit] if limit is not None else descriptors


def _rtsp_url(descriptor: CameraDescriptor) -> str | None:
    profile = descriptor.profile_for(StreamProtocol.RTSP)
    return profile.url if profile else None


async def _resolve_capture_url(
    descriptor: CameraDescriptor,
    settings: Settings,
    *,
    via_relay: bool,
) -> str | None:
    """Decide what this worker actually opens for a camera.

    For an external feed that is the *local relay path*, not the camera's own
    URL. MediaMTX holds a single connection to the gateway and fans it out to
    this pipeline and to every browser tile, instead of each consumer opening
    its own copy — see `sentinel_core.relay` for why that matters against the
    gateway's per-account viewing quota.

    `sourceOnDemand` is disabled for these paths: this worker is a permanent
    reader, and letting the path tear itself down between reconnects would add
    a fresh dial to every recovery.

    Falls back to dialling the camera directly if the relay cannot be set up,
    and says so loudly. A demo that keeps running on a degraded path is worth
    more than one that stops, but silently using twice the gateway's quota is
    exactly the bug this function exists to fix, so it must never be quiet.
    """
    url = _rtsp_url(descriptor)
    if url is None or not via_relay or is_relay_hosted(url, settings):
        return url

    path_name = relay_path_for(descriptor.camera_id, settings)
    async with httpx.AsyncClient(timeout=10.0) as relay_client:
        ok = await ensure_relay_path(
            rtsp_url=url,
            path_name=path_name,
            settings=settings,
            client=relay_client,
            on_demand=False,
        )
    if not ok:
        logger.warning(
            "%s: could not register relay path %r — falling back to dialling the camera "
            "directly. This opens a SECOND connection to the gateway for any camera also "
            "being previewed, against its per-account viewing quota.",
            descriptor.camera_id,
            path_name,
        )
        return url
    if path_name not in _WARMED_RELAY_PATHS:
        logger.info("%s: consuming via local relay path %s", descriptor.camera_id, path_name)
        _WARMED_RELAY_PATHS.add(path_name)
    return relay_rtsp_url(path_name, settings)


async def _release_warmed_paths(settings: Settings) -> None:
    """Hand back every relay path this worker pinned open.

    Without this, stopping the worker leaves MediaMTX dialling each camera
    forever with nothing reading it. That is invisible locally — no CPU, no
    log — but upstream it holds a live session against the gateway's viewing
    quota, and it accumulates: a survey that walks thirty cameras in batches
    leaves thirty pinned paths behind, which is enough to exhaust the quota
    and take the *next* run down before it starts.
    """
    if not _WARMED_RELAY_PATHS:
        return
    paths = sorted(_WARMED_RELAY_PATHS)
    logger.info("releasing %d relay path(s) back to on-demand: %s", len(paths), ", ".join(paths))
    async with httpx.AsyncClient(timeout=10.0) as relay_client:
        for path_name in paths:
            await release_relay_path(path_name=path_name, settings=settings, client=relay_client)
    _WARMED_RELAY_PATHS.clear()


async def _release_stale_relay_paths(settings: Settings, *, keep: set[str]) -> None:
    """Release paths a *previous* run pinned open and never handed back.

    Releasing on shutdown only works if there is a shutdown. A SIGKILL, a
    crash, a closed terminal or a flat battery all leave the paths pinned,
    and nothing in MediaMTX ever reconsiders: it goes on dialling those
    cameras indefinitely, spending a metered quota on a worker that no longer
    exists. Recovery cannot therefore depend on the dying process doing
    anything, so the next run cleans up instead — by which time it knows
    which paths are genuinely wanted and which are simply left over.

    Paths this run is about to use are kept: they are re-pinned moments later
    anyway, and releasing them first would drop a connection only to dial it
    straight back.
    """
    base = settings.relay_api_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as relay_client:
            response = await relay_client.get(f"{base}/v3/config/paths/list")
            if response.status_code != 200:
                return
            stale = [
                item["name"]
                for item in response.json().get("items", [])
                if item.get("sourceOnDemand") is False
                and item["name"].startswith("ext/")
                and item["name"] not in keep
            ]
            if not stale:
                return
            logger.warning(
                "releasing %d relay path(s) left pinned open by a previous run: %s",
                len(stale),
                ", ".join(stale),
            )
            for path_name in stale:
                await release_relay_path(
                    path_name=path_name, settings=settings, client=relay_client
                )
    except httpx.HTTPError as exc:
        logger.warning("could not reach the local relay to clean up stale paths: %s", exc)


async def _register_camera(client: httpx.AsyncClient, descriptor: CameraDescriptor) -> None:
    """Idempotent: 409 (already onboarded from a previous run) is expected
    and not an error — this worker does not own onboarding, the registry
    endpoints (M3) do; it just makes sure the FK target exists before it
    starts posting detections against it."""
    profile = descriptor.profile_for(StreamProtocol.RTSP)
    payload = {
        "camera_id": descriptor.camera_id,
        "name": descriptor.name,
        "driver_id": descriptor.driver_id,
        "department_name": descriptor.department,
        "site_name": descriptor.site,
        "location": descriptor.location.model_dump() if descriptor.location else None,
        "tier": descriptor.tier.value,
        "attributes": descriptor.attributes,
        "profiles": (
            [
                {
                    "protocol": profile.protocol.value,
                    "url": profile.url,
                    "codec": profile.codec,
                    "width": profile.width,
                    "height": profile.height,
                    "declared_fps": profile.declared_fps,
                }
            ]
            if profile
            else []
        ),
    }
    response = await client.post("/api/v1/cameras", json=payload)
    if response.status_code not in (201, 409):
        response.raise_for_status()


class _LoadMeter:
    """Analysis load in stream time: frames analysed per stream-second, and
    how far into the stream the worker has read. Both come from PTS, so this
    needs no wall clock (tests/test_compliance.py); the API compares the
    stream position with its own clock to report how far behind live the
    analysis is running."""

    def __init__(self) -> None:
        self.latest: FrameTiming | None = None
        self._analysed = 0
        self._window_start_pts: float | None = None

    def saw(self, timing: FrameTiming) -> None:
        if self.latest is not None and timing.seq < self.latest.seq:
            self._window_start_pts = None  # a new connection restarts PTS
        self.latest = timing
        if self._window_start_pts is None:
            self._window_start_pts = timing.pts_ms
            self._analysed = 0

    def analysed(self) -> None:
        self._analysed += 1

    def take_analysed_fps(self) -> float | None:
        if self.latest is None or self._window_start_pts is None:
            return None
        span_s = (self.latest.pts_ms - self._window_start_pts) / 1000.0
        if span_s <= 0:
            return None
        rate = self._analysed / span_s
        self._window_start_pts = self.latest.pts_ms
        self._analysed = 0
        return round(rate, 2)


async def _report_health(
    client: httpx.AsyncClient,
    camera_id: str,
    supervisor: CameraSupervisor,
    tamper_detector: TamperDetector | None = None,
    load: _LoadMeter | None = None,
) -> None:
    while True:
        await asyncio.sleep(HEALTH_REPORT_INTERVAL_S)
        payload: dict[str, Any] = {
            "status": supervisor.status.value,
            "measured_fps": supervisor.measured_fps,
            "declared_fps": supervisor.declared_fps,
            "reconnects": supervisor.reconnects,
            "discontinuities": supervisor.discontinuities,
            "tamper_status": tamper_detector.current_status if tamper_detector else None,
        }
        if load is not None:
            payload["analysed_fps"] = load.take_analysed_fps()
            if load.latest is not None:
                payload["stream_position_at"] = load.latest.observed_at.isoformat()
        try:
            response = await client.patch(f"/api/v1/cameras/{camera_id}/health", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("health report failed for %s: %s", camera_id, exc)


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _uploads_snapshots(settings: Settings) -> bool:
    """Whether evidence frames must be sent to the API rather than left in a
    snapshot directory the API already reads (see Settings.snapshot_upload)."""
    if settings.snapshot_upload != "auto":
        return settings.snapshot_upload == "always"
    return urlsplit(settings.core_api_url).hostname not in _LOCAL_HOSTS


OUTBOX_DRAIN_INTERVAL_S = 5.0


async def _deliver(
    client: httpx.AsyncClient,
    event_id: str,
    body: dict[str, Any],
    *,
    has_snapshot: bool,
    settings: Settings,
) -> Literal["ok", "retry", "rejected"]:
    """Post one detection (then its snapshot). `retry` when the API could not
    take it (unreachable, 5xx, rate-limited) so the caller queues it;
    `rejected` when the API refused this payload, which replaying cannot fix."""
    try:
        response = await client.post("/api/v1/detections", json=body)
    except httpx.TransportError as exc:
        logger.warning("detection post failed for %s: %s", event_id, exc)
        return "retry"
    if response.status_code >= 500 or response.status_code == 429:
        logger.warning("detection post for %s got HTTP %d", event_id, response.status_code)
        return "retry"
    if response.is_error:
        logger.warning(
            "API rejected detection %s (HTTP %d): %s",
            event_id,
            response.status_code,
            response.text[:200],
        )
        return "rejected"
    if has_snapshot:
        await _upload_snapshot(client, event_id, settings)
    return "ok"


async def _drain_outbox(
    client: httpx.AsyncClient, outbox: DetectionOutbox, settings: Settings
) -> None:
    """Replays queued detections oldest first. Live detections keep going
    straight to the API meanwhile, so a backlog never delays a fresh alert."""
    while True:
        await asyncio.sleep(OUTBOX_DRAIN_INTERVAL_S)
        replayed = 0
        for item in outbox.peek():
            outcome = await _deliver(
                client,
                item.event_id,
                item.payload,
                has_snapshot=item.has_snapshot,
                settings=settings,
            )
            if outcome == "retry":
                break  # still unreachable; try again next interval
            outbox.remove(item.event_id)
            replayed += outcome == "ok"
        if replayed:
            logger.info("replayed %d queued detection(s), %d still queued", replayed, len(outbox))


async def _upload_snapshot(client: httpx.AsyncClient, event_id: str, settings: Settings) -> None:
    blurred = Path(settings.snapshots_dir) / f"{event_id}.jpg"
    original = Path(settings.snapshot_originals_dir) / f"{event_id}.jpg"
    if not blurred.is_file():
        return  # the writer fails closed (no blur, no snapshot); nothing to send
    files = {"blurred": (blurred.name, blurred.read_bytes(), "image/jpeg")}
    if original.is_file():
        files["original"] = (original.name, original.read_bytes(), "image/jpeg")
    try:
        response = await client.put(f"/api/v1/detections/{event_id}/snapshot", files=files)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("snapshot upload failed for %s: %s", event_id, exc)


def _event_to_detection_payload(event: Event) -> dict[str, Any]:
    payload = event.payload
    # AnprPipeline only ever emits anpr.plate_read events (see
    # analytics/pipeline.py's _build_event) — this worker never sees a
    # HealthPayload, but the Event model's `payload` is a general union.
    assert isinstance(payload, AnprPayload)
    return {
        "event_id": event.event_id,
        "camera_id": event.camera_id,
        "plate_text": payload.plate_text,
        "plate_normalised": payload.plate_normalised,
        "plate_ambiguity_key": payload.plate_ambiguity_key,
        "plate_confidence": payload.plate_confidence,
        "format_valid": payload.format_valid,
        "frames_voted": payload.frames_voted,
        "vehicle_class": payload.vehicle.vehicle_class if payload.vehicle else None,
        "vehicle_colour": payload.vehicle.colour if payload.vehicle else None,
        "vehicle_track_id": payload.vehicle.track_id if payload.vehicle else None,
        "bbox": (
            {
                "x": payload.bbox.x,
                "y": payload.bbox.y,
                "width": payload.bbox.width,
                "height": payload.bbox.height,
            }
            if payload.bbox
            else None
        ),
        "pts_ms": event.pts_ms,
        "observed_at": event.observed_at.isoformat(),
        "node_id": event.pipeline.node_id,
        "model_versions": event.pipeline.models,
        "snapshot_uri": event.evidence.snapshot_uri,
    }


async def _run_camera(
    client: httpx.AsyncClient,
    descriptor: CameraDescriptor,
    vehicle_detector: VehicleDetector,
    plate_reader: FastAlprPlateReader,
    *,
    via_relay: bool = True,
    scheduler_config: SchedulerConfig | None = None,
    stop: asyncio.Event | None = None,
    outbox: DetectionOutbox | None = None,
) -> None:
    camera_id = descriptor.camera_id
    settings = get_settings()
    rtsp_url = await _resolve_capture_url(descriptor, settings, via_relay=via_relay)
    hls_profile = descriptor.profile_for(StreamProtocol.HLS)
    hls_url = hls_profile.url if hls_profile else None
    # RTSP first (via the relay); HLS is the integrator guide's fallback for a
    # network that blocks RTSP's port, and the only option for an HLS-only feed.
    candidates = [u for u in (rtsp_url, hls_url) if u]
    if not candidates:
        logger.warning("skipping %s: no rtsp or hls profile on file", camera_id)
        return

    # Re-assert the relay path before each retry. MediaMTX holds API-added
    # paths in memory only, so restarting the relay drops all of them and the
    # camera would otherwise retry forever against a path that no longer
    # exists — recoverable only by restarting the whole worker.
    async def _reassert_source() -> None:
        await _resolve_capture_url(descriptor, settings, via_relay=via_relay)

    scheduler = AnalysisScheduler(descriptor.tier, scheduler_config or SchedulerConfig())
    upload_snapshots = _uploads_snapshots(settings)
    supervisor = CameraSupervisor(
        config=CaptureConfig(
            camera_id=camera_id, url=candidates[0], fallback_urls=tuple(candidates[1:])
        ),
        on_reconnect=_reassert_source if via_relay and rtsp_url else None,
        decode_policy=scheduler.should_decode,
    )
    load = _LoadMeter()
    tamper_detector = TamperDetector()
    pipeline = AnprPipeline(
        vehicle_detector,
        plate_reader,
        node_id=settings.node_id,
        model_versions=MODEL_VERSIONS,
        snapshot_writer=SnapshotWriter(
            blurred_dir=Path(settings.snapshots_dir),
            originals_dir=Path(settings.snapshot_originals_dir),
        ),
        # Prefer the camera's own burned-in clock for observed_at. The grid
        # replays continuous recordings, so PTS-derived time says when we
        # processed a frame, not when the scene happened — months apart in
        # practice, and it is the scene's time that belongs in evidence.
        frame_clock=FrameClockReader(),
    )
    zone_engine = await _load_zone_engine(client, camera_id)

    health_task = asyncio.create_task(
        _report_health(client, camera_id, supervisor, tamper_detector, load)
    )
    stop_watch = asyncio.create_task(_stop_when_set(stop, supervisor)) if stop else None
    try:
        async for frame in supervisor.frames():
            load.saw(frame.timing)
            # M13: cheap (grayscale + Laplacian + a mean), so it runs on every
            # frame the scheduler decodes — no second inference engine.
            await asyncio.to_thread(tamper_detector.update, frame.image)
            # The scheduler already chose which frames to decode (tier and
            # PTS pacing; loop cuts always). Motion-gated cameras also skip
            # analysis while the scene is still.
            if not frame.timing.is_discontinuity and not scheduler.should_analyse(frame):
                continue
            load.analysed()
            events = await asyncio.to_thread(pipeline.process_frame, frame)
            for event in events:
                payload = event.payload
                assert isinstance(payload, AnprPayload)
                body = _event_to_detection_payload(event)
                has_snapshot = upload_snapshots and bool(event.evidence.snapshot_uri)
                outcome = await _deliver(
                    client, event.event_id, body, has_snapshot=has_snapshot, settings=settings
                )
                if outcome == "ok":
                    logger.info(
                        "%s: %s (%.2f)",
                        camera_id,
                        payload.plate_normalised,
                        payload.plate_confidence,
                    )
                elif outcome == "retry" and outbox is not None:
                    outbox.put(event.event_id, body, has_snapshot=has_snapshot)
                    logger.warning(
                        "%s: queued %s for replay (%d waiting)",
                        camera_id,
                        payload.plate_normalised,
                        len(outbox),
                    )

            if zone_engine is not None:
                await _evaluate_zones(client, camera_id, zone_engine, pipeline, frame)
    finally:
        health_task.cancel()
        if stop_watch is not None:
            stop_watch.cancel()


async def _stop_when_set(stop: asyncio.Event, supervisor: CameraSupervisor) -> None:
    """Ends the supervisor's frame loop at its next check, so it closes its
    own capture rather than having it closed underneath an in-flight read."""
    await stop.wait()
    supervisor.stop()


async def _release_camera_relay_path(settings: Settings, descriptor: CameraDescriptor) -> None:
    path_name = relay_path_for(descriptor.camera_id, settings)
    if path_name not in _WARMED_RELAY_PATHS:
        return
    async with httpx.AsyncClient(timeout=10.0) as relay_client:
        await release_relay_path(path_name=path_name, settings=settings, client=relay_client)
    _WARMED_RELAY_PATHS.discard(path_name)


async def _load_zone_engine(client: httpx.AsyncClient, camera_id: str) -> ZoneRuleEngine | None:
    """M13: fetches this camera's configured zones once at startup — an
    empty/missing config is the normal, expected state for a camera
    nobody has configured zone rules for yet, not an error."""
    try:
        response = await client.get(f"/api/v1/cameras/{camera_id}/zones")
        response.raise_for_status()
        zone_dicts = response.json()
    except httpx.HTTPError as exc:
        logger.warning("could not fetch zones for %s: %s", camera_id, exc)
        return None
    if not zone_dicts:
        return None
    zones = [
        Zone(
            zone_id=z["id"],
            name=z["name"],
            rule_type=z["rule_type"],
            polygon=tuple((p[0], p[1]) for p in z["polygon"]),
            dwell_threshold_s=z["dwell_threshold_s"],
            expected_direction_deg=z["expected_direction_deg"],
            direction_tolerance_deg=z["direction_tolerance_deg"],
            stopped_speed_threshold=z["stopped_speed_threshold"],
        )
        for z in zone_dicts
    ]
    logger.info("loaded %d zone rule(s) for %s", len(zones), camera_id)
    return ZoneRuleEngine(zones)


async def _evaluate_zones(
    client: httpx.AsyncClient,
    camera_id: str,
    zone_engine: ZoneRuleEngine,
    pipeline: AnprPipeline,
    frame: Frame[np.ndarray],
) -> None:
    height, width = frame.image.shape[:2]
    positions = {
        tracked.track_id: (
            (tracked.detection.bbox_xyxy[0] + tracked.detection.bbox_xyxy[2]) / 2 / width,
            (tracked.detection.bbox_xyxy[1] + tracked.detection.bbox_xyxy[3]) / 2 / height,
        )
        for tracked in pipeline.last_tracked_vehicles
    }
    zone_events = zone_engine.update(positions, now_s=frame.timing.pts_ms / 1000.0)
    for zone_event in zone_events:
        try:
            response = await client.post(
                "/api/v1/zone-events",
                json={
                    "zone_id": zone_event.zone_id,
                    "camera_id": camera_id,
                    "rule_type": zone_event.rule_type,
                    "track_id": str(zone_event.track_id),
                    "dwell_time_s": zone_event.dwell_time_s,
                    "heading_deg": zone_event.heading_deg,
                    "observed_at": frame.observed_at.isoformat(),
                },
            )
            response.raise_for_status()
            logger.info(
                "%s: zone rule '%s' fired (%s)",
                camera_id,
                zone_event.rule_type,
                zone_event.zone_name,
            )
        except httpx.HTTPError as exc:
            logger.warning("zone event post failed for %s: %s", camera_id, exc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        choices=["synthetic", "gov", "registry"],
        default="synthetic",
        help="synthetic: local M1 RTSP grid (default). gov: the real Sentinel Camera Grid. "
        "registry: every camera onboarded into the core API, re-read periodically.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"cap on concurrent cameras (default: unlimited for synthetic, "
        f"{DEFAULT_GOV_LIMIT} for gov — see the integrator guide's 'pace your load' note).",
    )
    parser.add_argument(
        "--cameras",
        type=str,
        default=None,
        help="comma-separated camera ids to run instead of the first --limit from the catalogue "
        "(e.g. cam01,cam04).",
    )
    parser.add_argument(
        "--sampled-fps",
        type=float,
        default=SchedulerConfig().sampled_fps,
        help="analysis rate for b_sampled cameras (and c_motion_gated ones while there is "
        "motion), paced by stream timestamps. Lower it to fit more cameras on one machine.",
    )
    parser.add_argument(
        "--department",
        type=str,
        default=None,
        help="only analyse cameras registered to this department (case-insensitive) — shard a "
        "large registry across several workers, one per department or district.",
    )
    parser.add_argument(
        "--resync-interval",
        type=float,
        default=DEFAULT_RESYNC_INTERVAL_S,
        help=f"--source registry only: seconds between registry re-reads (default "
        f"{DEFAULT_RESYNC_INTERVAL_S:.0f}; 0 reads it once).",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="dial each camera directly instead of consuming it through the local relay. "
        "Opens one gateway connection per consumer rather than per camera, so a camera that "
        "is also being previewed costs two — only use this to isolate a relay problem.",
    )
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=1,
        help="a_continuous cameras: run ANPR on every Nth frame (default 1: every frame). "
        "Other tiers are paced by --sampled-fps instead. Vehicle detection and plate OCR are "
        "the dominant cost — four 1080p cameras at 25fps saturate an 8-core machine, which "
        "starves the relay's HLS muxer and stalls live preview.",
    )
    return parser.parse_args()


async def _load_descriptors(
    args: argparse.Namespace, settings: Settings, client: httpx.AsyncClient
) -> tuple[list[CameraDescriptor], int | None]:
    """The source's camera list and its default --limit."""
    if args.source == "synthetic":
        return _load_synthetic_descriptors(), None
    if args.source == "registry":
        try:
            return await _fetch_registry_descriptors(client), None
        except httpx.HTTPError as exc:
            raise SystemExit(
                f"could not read the camera registry from {settings.core_api_url}: {exc}\n"
                "Is the core API running (`make api`) and SENTINEL_EDGE_SERVICE_TOKEN the same "
                "for both processes?"
            ) from exc
    if not settings.gov_access_email:
        raise SystemExit(
            "no SENTINEL_GOV_ACCESS_EMAIL/PASSWORD configured — set them in .env "
            "(see .env.example) to use --source gov."
        )
    async with GovCatalogueClient(settings) as gov_client:
        return await gov_client.fetch(), DEFAULT_GOV_LIMIT


async def _resync_forever(
    args: argparse.Namespace, client: httpx.AsyncClient, fleet: CameraFleet
) -> None:
    while True:
        await asyncio.sleep(args.resync_interval)
        try:
            available = await _fetch_registry_descriptors(client)
        except httpx.HTTPError as exc:
            # Keep analysing what is already running: a registry blip must
            # not stop every camera.
            logger.warning("registry re-read failed, keeping current cameras: %s", exc)
            continue
        wanted = _select_cameras(
            available,
            cameras=args.cameras,
            limit=args.limit,
            department=args.department,
            warn_missing=False,
        )
        changes = await fleet.sync(wanted)
        if changes:
            logger.info(
                "registry resync: started %s, restarted %s, stopped %s (now %d camera(s))",
                changes.started or "-",
                changes.restarted or "-",
                changes.stopped or "-",
                len(fleet.camera_ids),
            )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    args = _parse_args()

    if not VEHICLE_MODEL.exists():
        raise SystemExit(
            f"no vehicle model at {VEHICLE_MODEL}. Run:\n"
            "    uv run --isolated --with ultralytics --with onnx "
            "python scripts/export_models.py"
        )

    settings = get_settings()
    api_base_url = settings.core_api_url

    # Every call this worker makes is machine-to-machine (camera
    # registration, health heartbeats, detection ingest) — the shared
    # service token (not a human's JWT, which this process has no user to
    # log in as) is attached once here so every request through this client
    # carries it, rather than threading it through each call site.
    service_headers = {"X-Service-Token": settings.edge_service_token.get_secret_value()}
    async with httpx.AsyncClient(
        base_url=api_base_url, timeout=10.0, headers=service_headers
    ) as client:
        available, default_limit = await _load_descriptors(args, settings, client)
        descriptors = _select_cameras(
            available,
            cameras=args.cameras,
            limit=args.limit if args.limit is not None else default_limit,
            department=args.department,
        )
        watch_registry = args.source == "registry" and args.resync_interval > 0
        if not descriptors and not watch_registry:
            raise SystemExit("no cameras to run — check --source/--cameras/--limit/--department")

        logger.info("loading models ...")
        vehicle_detector = VehicleDetector(VEHICLE_MODEL)
        plate_reader = FastAlprPlateReader()
        logger.info(
            "models loaded; vehicle detector providers: %s", vehicle_detector.providers_in_use
        )

        if args.source != "registry":
            # Registry cameras exist by definition; catalogue and synthetic
            # ones need their FK target created before detections arrive.
            for descriptor in descriptors:
                await _register_camera(client, descriptor)

        via_relay = not args.direct
        if via_relay:
            await _release_stale_relay_paths(
                settings, keep={relay_path_for(d.camera_id, settings) for d in descriptors}
            )
        logger.info(
            "starting %d camera pipeline(s) (source=%s, transport=%s, continuous stride=%d, "
            "sampled %.1f fps%s) against %s",
            len(descriptors),
            args.source,
            "local relay" if via_relay else "direct to camera",
            args.frame_stride,
            args.sampled_fps,
            f", registry re-read every {args.resync_interval:.0f}s" if watch_registry else "",
            api_base_url,
        )
        if not descriptors:
            logger.warning(
                "the registry has no analysable cameras yet — onboard some (wizard, bulk CSV or "
                "device discovery) and they will be picked up on the next re-read"
            )

        scheduler_config = SchedulerConfig(stride=args.frame_stride, sampled_fps=args.sampled_fps)
        outbox = DetectionOutbox(Path(settings.edge_outbox_path))
        if queued := len(outbox):
            logger.info("%d detection(s) queued from an earlier run will be replayed", queued)
        drain = asyncio.create_task(_drain_outbox(client, outbox, settings))

        async def _run(descriptor: CameraDescriptor, stop: asyncio.Event) -> None:
            await _run_camera(
                client,
                descriptor,
                vehicle_detector,
                plate_reader,
                via_relay=via_relay,
                scheduler_config=scheduler_config,
                stop=stop,
                outbox=outbox,
            )

        async def _on_removed(descriptor: CameraDescriptor) -> None:
            if via_relay:
                await _release_camera_relay_path(settings, descriptor)

        fleet = CameraFleet(_run, on_removed=_on_removed)
        await fleet.sync(descriptors)
        supervise = asyncio.create_task(
            _resync_forever(args, client, fleet) if watch_registry else fleet.wait()
        )
        try:
            # Without this, SIGTERM — which is how this process is actually
            # stopped, by `kill`, a container stop or a supervisor — takes the
            # interpreter down where it stands, and the `finally` below never
            # runs. The relay paths would then stay pinned open exactly as if
            # the release had never been written. Turning the signal into a
            # cancellation lets the stack unwind normally instead. SIGHUP is
            # included because a worker started from a terminal receives it
            # when that terminal goes away, which is how this leaked in
            # practice; SIGKILL cannot be caught at all, which is why startup
            # also sweeps up whatever a previous run left behind.
            loop = asyncio.get_running_loop()
            for signame in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                loop.add_signal_handler(signame, supervise.cancel)
            try:
                await supervise
            except asyncio.CancelledError:
                logger.info("shutting down on signal")
        finally:
            drain.cancel()
            await fleet.cancel_all()
            await _release_warmed_paths(settings)
            outbox.close()


if __name__ == "__main__":
    asyncio.run(main())
