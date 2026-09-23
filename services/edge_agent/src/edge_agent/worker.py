"""Live edge worker: the process that actually ties capture, ANPR and the
API together, rather than each being proven only in isolation (unit tests
with fake ports) or via manual curl (M4/M5 verification).

Per camera: `CameraSupervisor` owns reconnect/backoff, `AnprPipeline` turns
frames into resolved-plate events, and this module posts each event to
`POST /api/v1/detections` and periodically PATCHes camera health. Detector
and OCR models are loaded once and shared across every camera's pipeline —
they are stateless inference engines; only the tracker/voter state in each
`AnprPipeline` instance is per-camera.

Two camera sources, selected with `--source`:

- `synthetic` (default): the M1 local RTSP grid
  (`scripts/synthetic_grid.py`) — 8 cameras, unlimited concurrency, no
  external network dependency.
- `gov`: the real Sentinel Camera Grid (the organisers' actual integration
  target), fetched live via `GovCatalogueClient` — 30 cameras as of this
  writing. The integrator guide explicitly asks integrators to "pace your
  load" and open only the cameras being processed, so this defaults to a
  small `--limit` rather than opening all 30 RTSP connections at once.

Usage (with the docker-compose stack and core_api already running — see
README/docs/05-DELIVERY-PLAN.md):

    uv run --package edge-agent python -m edge_agent.worker
    uv run --package edge-agent python -m edge_agent.worker --source gov --limit 4
    uv run --package edge-agent python -m edge_agent.worker --source gov --cameras cam01,cam04
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from edge_agent.analytics.frame_clock import FrameClockReader
from edge_agent.analytics.pipeline import AnprPipeline
from edge_agent.analytics.plate_reader import FastAlprPlateReader
from edge_agent.analytics.snapshot_writer import SnapshotWriter
from edge_agent.analytics.tamper import TamperDetector
from edge_agent.analytics.vehicle_detector import VehicleDetector
from edge_agent.analytics.zone_rules import Zone, ZoneRuleEngine
from edge_agent.pipeline.capture import CaptureConfig
from edge_agent.pipeline.supervisor import CameraSupervisor
from sentinel_core.clock import Frame
from sentinel_core.config import Settings, get_settings
from sentinel_core.gov_catalogue import GovCatalogueClient
from sentinel_core.relay import (
    ensure_relay_path,
    is_relay_hosted,
    relay_path_for,
    relay_rtsp_url,
    release_relay_path,
)
from sentinel_core.schemas import AnprPayload, CameraDescriptor, Event, StreamProtocol

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
    "ocr": "cct-s-v2-global@fast-plate-ocr-1.1.0",
}
HEALTH_REPORT_INTERVAL_S = 5.0
DEFAULT_GOV_LIMIT = 4


def _load_synthetic_descriptors() -> list[CameraDescriptor]:
    if not SYNTHETIC_CATALOGUE.exists():
        raise SystemExit(
            f"no catalogue at {SYNTHETIC_CATALOGUE}. Run:\n"
            "    uv run python scripts/synthetic_grid.py generate\n"
            "    uv run python scripts/synthetic_grid.py start"
        )
    raw: list[dict[str, Any]] = json.loads(SYNTHETIC_CATALOGUE.read_text())
    return [CameraDescriptor.model_validate(entry) for entry in raw]


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


async def _report_health(
    client: httpx.AsyncClient,
    camera_id: str,
    supervisor: CameraSupervisor,
    tamper_detector: TamperDetector | None = None,
) -> None:
    while True:
        await asyncio.sleep(HEALTH_REPORT_INTERVAL_S)
        payload = {
            "status": supervisor.status.value,
            "measured_fps": supervisor.measured_fps,
            "declared_fps": supervisor.declared_fps,
            "reconnects": supervisor.reconnects,
            "discontinuities": supervisor.discontinuities,
            "tamper_status": tamper_detector.current_status if tamper_detector else None,
        }
        try:
            response = await client.patch(f"/api/v1/cameras/{camera_id}/health", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("health report failed for %s: %s", camera_id, exc)


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
) -> None:
    camera_id = descriptor.camera_id
    settings = get_settings()
    url = await _resolve_capture_url(descriptor, settings, via_relay=via_relay)
    if url is None:
        logger.warning("skipping %s: no rtsp profile in the catalogue", camera_id)
        return

    supervisor = CameraSupervisor(config=CaptureConfig(camera_id=camera_id, url=url))
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
        _report_health(client, camera_id, supervisor, tamper_detector)
    )
    try:
        async for frame in supervisor.frames():
            # M13: cheap enough to run on every frame (grayscale + Laplacian
            # + a mean) — no second inference engine, unlike the ANPR
            # pipeline's own per-frame cost.
            await asyncio.to_thread(tamper_detector.update, frame.image)
            events = await asyncio.to_thread(pipeline.process_frame, frame)
            for event in events:
                payload = event.payload
                assert isinstance(payload, AnprPayload)
                try:
                    response = await client.post(
                        "/api/v1/detections", json=_event_to_detection_payload(event)
                    )
                    response.raise_for_status()
                    logger.info(
                        "%s: %s (%.2f)",
                        camera_id,
                        payload.plate_normalised,
                        payload.plate_confidence,
                    )
                except httpx.HTTPError as exc:
                    logger.warning("detection post failed for %s: %s", camera_id, exc)

            if zone_engine is not None:
                await _evaluate_zones(client, camera_id, zone_engine, pipeline, frame)
    finally:
        health_task.cancel()


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
        choices=["synthetic", "gov"],
        default="synthetic",
        help="synthetic: local M1 RTSP grid (default). gov: the real Sentinel Camera Grid.",
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
        "--direct",
        action="store_true",
        help="dial each camera directly instead of consuming it through the local relay. "
        "Opens one gateway connection per consumer rather than per camera, so a camera that "
        "is also being previewed costs two — only use this to isolate a relay problem.",
    )
    return parser.parse_args()


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

    if args.source == "synthetic":
        descriptors = _load_synthetic_descriptors()
        default_limit = None
    else:
        if not settings.gov_access_email:
            raise SystemExit(
                "no SENTINEL_GOV_ACCESS_EMAIL/PASSWORD configured — set them in .env "
                "(see .env.example) to use --source gov."
            )
        async with GovCatalogueClient(settings) as gov_client:
            descriptors = await gov_client.fetch()
        default_limit = DEFAULT_GOV_LIMIT

    if args.cameras:
        wanted = set(args.cameras.split(","))
        descriptors = [d for d in descriptors if d.camera_id in wanted]
        missing = wanted - {d.camera_id for d in descriptors}
        if missing:
            logger.warning("requested camera ids not found in the catalogue: %s", sorted(missing))
    else:
        limit = args.limit if args.limit is not None else default_limit
        if limit is not None:
            descriptors = descriptors[:limit]

    if not descriptors:
        raise SystemExit("no cameras to run — check --source/--cameras/--limit")

    logger.info("loading models ...")
    vehicle_detector = VehicleDetector(VEHICLE_MODEL)
    plate_reader = FastAlprPlateReader()
    logger.info("models loaded; vehicle detector providers: %s", vehicle_detector.providers_in_use)

    # Every call this worker makes is machine-to-machine (camera
    # registration, health heartbeats, detection ingest) — the shared
    # service token (not a human's JWT, which this process has no user to
    # log in as) is attached once here so every request through this client
    # carries it, rather than threading it through each call site.
    service_headers = {"X-Service-Token": settings.edge_service_token.get_secret_value()}
    async with httpx.AsyncClient(
        base_url=api_base_url, timeout=10.0, headers=service_headers
    ) as client:
        for descriptor in descriptors:
            await _register_camera(client, descriptor)

        via_relay = not args.direct
        logger.info(
            "starting %d camera pipeline(s) (source=%s, transport=%s) against %s",
            len(descriptors),
            args.source,
            "local relay" if via_relay else "direct to camera",
            api_base_url,
        )
        try:
            await asyncio.gather(
                *(
                    _run_camera(
                        client, descriptor, vehicle_detector, plate_reader, via_relay=via_relay
                    )
                    for descriptor in descriptors
                )
            )
        finally:
            await _release_warmed_paths(settings)


if __name__ == "__main__":
    asyncio.run(main())
