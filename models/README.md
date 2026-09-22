# Model weights

Nothing in this directory is committed — `weights/` is gitignored (`*.onnx`, `*.pt`,
`*.mlpackage`). Weights are downloaded/exported on demand:

| Model | How to get it | Licence |
|---|---|---|
| Vehicle detector (YOLO11n → ONNX) | `uv run --isolated --with ultralytics --with onnx python scripts/export_models.py` | AGPL-3.0 (Ultralytics) — documented and accepted, see [docs/02-ANPR-PIPELINE.md](../docs/02-ANPR-PIPELINE.md) section 8 |
| Plate detector (`yolo-v9-t-640-license-plate-end2end`) | Downloaded automatically on first use by `open-image-models` (via `edge_agent.analytics.plate_reader`) | MIT |
| OCR (`cct-s-v2-global-model`) | Downloaded automatically on first use by `fast-plate-ocr` | MIT |

The vehicle detector export runs in an **isolated** ephemeral environment (`--isolated`),
never installed into this project's own venv — see `scripts/export_models.py`'s docstring
for why that matters (it is not just tidiness: ultralytics pins plain `opencv-python`,
which conflicts with our `opencv-python-headless` runtime dependency if both land in one
venv).

See [docs/02-ANPR-PIPELINE.md](../docs/02-ANPR-PIPELINE.md) for model selection rationale,
measured Apple Silicon benchmarks, and the licence position for every component.
