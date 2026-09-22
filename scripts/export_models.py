#!/usr/bin/env python3
"""Export the vehicle detector to ONNX.

Dev-time only: this needs `ultralytics` (and therefore torch), which is
deliberately NOT installed into this project's shared venv — production
inference uses onnxruntime exclusively (see 02-ANPR-PIPELINE.md section 2).

Run it in an isolated, throwaway environment instead:

    uv run --isolated --with ultralytics --with onnx python scripts/export_models.py

`--isolated` never touches this workspace's own venv. This matters in
practice, not just in principle: ultralytics pins plain `opencv-python`,
which provides the same `cv2` module as our `opencv-python-headless` runtime
dependency, and installing both into ONE shared venv leaves a broken,
conflicting cv2 install behind — that happened once while building this.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_DIR = REPO_ROOT / "models" / "weights"

# AGPL-3.0 (Ultralytics). Documented and accepted per 02-ANPR-PIPELINE.md
# section 8 — the challenge mandates open-source technologies and AGPL-3.0
# is OSI-approved. An Apache-only migration path (RF-DETR) is noted there.
VEHICLE_MODEL = "yolo11n.pt"
VEHICLE_MODEL_ONNX = "yolo11n.onnx"

# COCO class ids for vehicle-relevant categories, kept alongside the export
# so the detector wrapper doesn't need to import ultralytics/torch at all.
VEHICLE_CLASS_IDS = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "ultralytics is not installed in this environment (by design — see the "
            "module docstring). Run:\n"
            "    uv run --isolated --with ultralytics --with onnx "
            "python scripts/export_models.py",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = WEIGHTS_DIR / VEHICLE_MODEL_ONNX
    if onnx_path.exists():
        print(f"already exported: {onnx_path}")
        return

    print(f"downloading {VEHICLE_MODEL} and exporting to ONNX ...")
    model = YOLO(VEHICLE_MODEL)
    # opset=17 + simplify=True: the measured working path for the ORT CoreML
    # EP on Apple Silicon — a naive .mlpackage export currently fails on the
    # C2PSA attention block (see 02-ANPR-PIPELINE.md section 3.1).
    exported = model.export(format="onnx", opset=17, simplify=True, imgsz=640)
    exported_path = Path(exported)
    exported_path.rename(onnx_path)

    # ultralytics also drops a .pt file and export artefacts in the cwd;
    # keep only the ONNX weights this project actually uses.
    stray_pt = Path(VEHICLE_MODEL)
    if stray_pt.exists():
        stray_pt.unlink()

    print(f"exported: {onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB)")
    print(f"vehicle class ids: {VEHICLE_CLASS_IDS}")


if __name__ == "__main__":
    main()
