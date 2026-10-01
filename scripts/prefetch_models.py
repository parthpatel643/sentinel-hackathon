#!/usr/bin/env python3
"""Download every model the edge worker needs, so it can run with no
internet — a police network, a venue VLAN, a hotspot that drops.

The vehicle detector is exported locally (scripts/export_models.py); the
plate detector, plate OCR and face detector are fetched on first use and
cached under ~/.cache. First use on an isolated network is the wrong time to
discover that, so run this once while online and check with `make doctor`.

    uv run --package edge-agent python scripts/prefetch_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VEHICLE_MODEL = REPO_ROOT / "models" / "weights" / "yolo11n.onnx"


def main() -> int:
    from edge_agent.analytics.face_blur import ensure_model_downloaded
    from edge_agent.analytics.plate_reader import FastAlprPlateReader

    failed = False
    if VEHICLE_MODEL.exists():
        print(f"ok    vehicle detector   {VEHICLE_MODEL}")
    else:
        failed = True
        print(
            f"MISSING vehicle detector {VEHICLE_MODEL}\n"
            "      uv run --isolated --with ultralytics --with onnx python scripts/export_models.py"
        )

    try:
        FastAlprPlateReader()
        print("ok    plate detector + OCR (cached by open-image-models / fast-plate-ocr)")
    except Exception as exc:
        failed = True
        print(f"FAILED plate detector + OCR: {exc}")

    try:
        print(f"ok    face detector      {ensure_model_downloaded()}")
    except Exception as exc:
        failed = True
        print(f"FAILED face detector: {exc}")

    print("\nall models available offline" if not failed else "\nsome models are missing")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
