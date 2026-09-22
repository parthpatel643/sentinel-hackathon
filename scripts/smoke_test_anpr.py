#!/usr/bin/env python3
"""Real-model ANPR smoke test.

Unlike the pytest suite (which injects fake vehicle-detector/plate-reader
ports so CI never needs model weights or network access — see
services/edge_agent/tests/test_anpr_pipeline.py), this script runs the ACTUAL
ONNX vehicle detector and fast-alpr plate reader end to end, so a human can
sanity-check the real thing works after any model or dependency change.

Usage:
    uv run python scripts/export_models.py   # if models/weights/yolo11n.onnx
                                              # does not exist yet (see that
                                              # script's own docstring for the
                                              # isolated-environment command)
    uv run python scripts/smoke_test_anpr.py [image_path]
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "sentinel_core" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "edge_agent" / "src"))

DEFAULT_IMAGE = REPO_ROOT / "var" / "test-images" / "plate.png"
VEHICLE_MODEL = REPO_ROOT / "models" / "weights" / "yolo11n.onnx"


def main() -> None:
    import cv2

    from edge_agent.analytics.pipeline import AnprPipeline
    from edge_agent.analytics.plate_reader import FastAlprPlateReader
    from edge_agent.analytics.vehicle_detector import VehicleDetector
    from sentinel_core.clock import Frame, FrameTiming

    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE
    if not image_path.exists():
        print(f"no test image at {image_path}", file=sys.stderr)
        raise SystemExit(1)
    if not VEHICLE_MODEL.exists():
        print(
            f"vehicle model not found at {VEHICLE_MODEL}. Run:\n"
            "    uv run --isolated --with ultralytics --with onnx "
            "python scripts/export_models.py",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("loading models ...")
    t0 = time.time()
    vehicle_detector = VehicleDetector(VEHICLE_MODEL)
    plate_reader = FastAlprPlateReader()
    print(f"  loaded in {time.time() - t0:.2f}s")
    print(f"  vehicle detector providers: {vehicle_detector.providers_in_use}")

    pipeline = AnprPipeline(
        vehicle_detector,
        plate_reader,
        node_id="smoke-test",
        model_versions={
            "vehicle_det": "yolo11n@ultralytics-8.4.158",
            "plate_det": "yolo-v9-t-640@open-image-models-0.6.0",
            "ocr": "cct-s-v2-global@fast-plate-ocr-1.1.0",
        },
    )

    image = cv2.imread(str(image_path))
    if image is None:
        print(f"could not decode {image_path}", file=sys.stderr)
        raise SystemExit(1)

    now = datetime.now(UTC)
    timing = FrameTiming(
        camera_id="smoke-test-cam",
        pts_ms=40.0,
        seq=0,
        stream_epoch=now,
        observed_at=now,
        delta_ms=40.0,
        is_gap=False,
        is_discontinuity=False,
    )
    frame = Frame(timing=timing, image=image, width=image.shape[1], height=image.shape[0])

    print(f"\nrunning the pipeline on {image_path} ({image.shape[1]}x{image.shape[0]}) ...")
    t0 = time.time()
    events = pipeline.process_frame(frame)
    latency_ms = (time.time() - t0) * 1000

    print(f"  {latency_ms:.1f} ms, {len(events)} plate event(s)\n")
    if not events:
        print(
            "No plates read. This is a smoke test on ONE static image with "
            "unknown ground truth - it proves the pipeline runs end to end, "
            "not that accuracy is acceptable. See the M2 eval-set milestone "
            "for an actual accuracy measurement on a labelled holdout."
        )
        return

    for event in events:
        payload = event.payload
        print(f"  plate:         {payload.plate_text}")
        print(f"  normalised:    {payload.plate_normalised}")
        print(f"  ambiguity key: {payload.plate_ambiguity_key}")
        print(f"  confidence:    {payload.plate_confidence:.3f}")
        print(
            f"  format valid:  {payload.format_valid}  (Indian grammar - a non-Indian "
            "test plate correctly reads False here, that is not a bug)"
        )
        print(
            f"  vehicle:       {payload.vehicle.vehicle_class} (track {payload.vehicle.track_id})"
        )
        print(f"  model versions: {event.pipeline.models}")
        print()


if __name__ == "__main__":
    main()
