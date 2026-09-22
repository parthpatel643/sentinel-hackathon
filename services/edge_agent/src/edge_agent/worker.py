"""Live edge worker: the process that actually ties capture, ANPR and the
API together, rather than each being proven only in isolation (unit tests
with fake ports) or via manual curl (M4/M5 verification).

Per camera in the catalogue: `CameraSupervisor` owns reconnect/backoff,
`AnprPipeline` turns frames into resolved-plate events, and this module posts
each event to `POST /api/v1/detections` and periodically PATCHes camera
health. Detector and OCR models are loaded once and shared across every
camera's pipeline — they are stateless inference engines; only the
tracker/voter state in each `AnprPipeline` instance is per-camera.

Usage (with the docker-compose stack, core_api and the synthetic grid all
already running — see README/docs/05-DELIVERY-PLAN.md):

    uv run --package edge-agent python -m edge_agent.worker
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from edge_agent.analytics.pipeline import AnprPipeline
from edge_agent.analytics.plate_reader import FastAlprPlateReader
from edge_agent.analytics.vehicle_detector import VehicleDetector
from edge_agent.pipeline.capture import CaptureConfig
from edge_agent.pipeline.supervisor import CameraSupervisor
from sentinel_core.config import get_settings
from sentinel_core.schemas import AnprPayload, Event

logger = logging.getLogger("edge_agent.worker")

REPO_ROOT = Path(__file__).resolve().parents[4]
SYNTHETIC_CATALOGUE = REPO_ROOT / "var" / "synthetic-grid" / "catalogue.json"
VEHICLE_MODEL = REPO_ROOT / "models" / "weights" / "yolo11n.onnx"
MODEL_VERSIONS = {
    "vehicle_det": "yolo11n@ultralytics-8.4.158",
    "plate_det": "yolo-v9-t-640@open-image-models-0.6.0",
    "ocr": "cct-s-v2-global@fast-plate-ocr-1.1.0",
}
HEALTH_REPORT_INTERVAL_S = 5.0

# The catalogue is parsed straight from JSON (the same shape
# `sentinel_core.schemas.CameraDescriptor` serialises to) rather than
# re-validated into that model — this worker only reads a handful of known
# keys back out, so the extra round trip isn't worth the ceremony.
CameraJson = dict[str, Any]


def _rtsp_url(descriptor: CameraJson) -> str | None:
    for profile in descriptor.get("profiles", []):
        if profile.get("protocol") == "rtsp":
            url = profile["url"]
            assert isinstance(url, str)
            return url
    return None


async def _register_camera(client: httpx.AsyncClient, descriptor: CameraJson) -> None:
    """Idempotent: 409 (already onboarded from a previous run) is expected
    and not an error — this worker does not own onboarding, the registry
    endpoints (M3) do; it just makes sure the FK target exists before it
    starts posting detections against it."""
    profile = next((p for p in descriptor.get("profiles", []) if p.get("protocol") == "rtsp"), None)
    payload = {
        "camera_id": descriptor["camera_id"],
        "name": descriptor["name"],
        "driver_id": descriptor.get("driver_id", "rtsp"),
        "department_name": descriptor.get("department"),
        "site_name": descriptor.get("site"),
        "location": descriptor.get("location"),
        "tier": descriptor.get("tier", "b_sampled"),
        "attributes": descriptor.get("attributes", {}),
        "profiles": [profile] if profile else [],
    }
    response = await client.post("/api/v1/cameras", json=payload)
    if response.status_code not in (201, 409):
        response.raise_for_status()


async def _report_health(
    client: httpx.AsyncClient, camera_id: str, supervisor: CameraSupervisor
) -> None:
    while True:
        await asyncio.sleep(HEALTH_REPORT_INTERVAL_S)
        payload = {
            "status": supervisor.status.value,
            "measured_fps": supervisor.measured_fps,
            "declared_fps": supervisor.declared_fps,
            "reconnects": supervisor.reconnects,
            "discontinuities": supervisor.discontinuities,
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
    }


async def _run_camera(
    client: httpx.AsyncClient,
    descriptor: CameraJson,
    vehicle_detector: VehicleDetector,
    plate_reader: FastAlprPlateReader,
) -> None:
    camera_id = descriptor["camera_id"]
    url = _rtsp_url(descriptor)
    if url is None:
        logger.warning("skipping %s: no rtsp profile in the catalogue", camera_id)
        return

    supervisor = CameraSupervisor(config=CaptureConfig(camera_id=camera_id, url=url))
    pipeline = AnprPipeline(
        vehicle_detector,
        plate_reader,
        node_id=get_settings().node_id,
        model_versions=MODEL_VERSIONS,
    )

    health_task = asyncio.create_task(_report_health(client, camera_id, supervisor))
    try:
        async for frame in supervisor.frames():
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
    finally:
        health_task.cancel()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    if not SYNTHETIC_CATALOGUE.exists():
        raise SystemExit(
            f"no catalogue at {SYNTHETIC_CATALOGUE}. Run:\n"
            "    uv run python scripts/synthetic_grid.py generate\n"
            "    uv run python scripts/synthetic_grid.py start"
        )
    if not VEHICLE_MODEL.exists():
        raise SystemExit(
            f"no vehicle model at {VEHICLE_MODEL}. Run:\n"
            "    uv run --isolated --with ultralytics --with onnx "
            "python scripts/export_models.py"
        )

    descriptors: list[CameraJson] = json.loads(SYNTHETIC_CATALOGUE.read_text())
    settings = get_settings()
    api_base_url = settings.core_api_url

    logger.info("loading models ...")
    vehicle_detector = VehicleDetector(VEHICLE_MODEL)
    plate_reader = FastAlprPlateReader()
    logger.info("models loaded; vehicle detector providers: %s", vehicle_detector.providers_in_use)

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        for descriptor in descriptors:
            await _register_camera(client, descriptor)

        logger.info("starting %d camera pipelines against %s", len(descriptors), api_base_url)
        await asyncio.gather(
            *(
                _run_camera(client, descriptor, vehicle_detector, plate_reader)
                for descriptor in descriptors
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
