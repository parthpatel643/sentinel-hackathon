"""Plate detection + OCR, wrapping `fast_alpr.ALPR`.

Wrapped rather than called directly so (a) the two measured execution-provider
findings from 02-ANPR-PIPELINE.md section 3 are applied by default instead of
left to auto-selection, and (b) the rest of the pipeline depends on our own
small `PlateReader` port, not on fast_alpr's API shape — a future swap to a
different detector/OCR pair (e.g. PARSeq as a low-confidence fallback) is an
implementation, not a rewrite of every call site.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from fast_alpr import ALPR

__all__ = ["PLATE_PAD_X", "PLATE_PAD_Y", "FastAlprPlateReader", "PlateCandidate"]

# Share of the plate box added on each side before OCR. Measured on the
# hand-labelled holdout (evidence/ANPR-ACCURACY.md) together with the OCR
# model choice below.
PLATE_PAD_X = 0.10
PLATE_PAD_Y = 0.15


@dataclass(frozen=True, slots=True)
class PlateCandidate:
    """One raw plate read, before temporal voting or Indian-grammar
    validation — see analytics/voting.py for what happens next."""

    text: str
    char_confidences: tuple[float, ...]
    bbox_xyxy: tuple[float, float, float, float]

    @property
    def mean_confidence(self) -> float:
        return (
            sum(self.char_confidences) / len(self.char_confidences)
            if self.char_confidences
            else 0.0
        )


class FastAlprPlateReader:
    """Default execution-provider policy.

    OCR on CPU EP, explicitly pinned: CoreML makes the CCT OCR models
    *slower* (attention-op partitioning overhead dominates a sub-2ms
    model) — the opposite of what fast-plate-ocr's own docs suggest for the
    *legacy* CNN models. Do not trust automatic provider selection for this
    stage.

    The plate DETECTOR defaults to CPU too, despite CoreML measuring
    5-8.6x faster for this model family on Apple Silicon
    (docs/02-ANPR-PIPELINE.md section 3) — that benchmark was run against
    the M2 synthetic grid and a static test image, both of which happened
    never to trigger a real CoreML bug: this end-to-end YOLOv9 export's
    baked-in NMS produces a zero-length dynamic array on some real frames,
    which CoreML's EP cannot execute
    ("dynamic shape ({-1}) but the runtime shape ({0}) has zero elements")
    and CPU EP handles without issue. Found running this pipeline against
    the real government camera grid for the first time — every frame from
    two live cameras hit it within two minutes, effectively disabling plate
    detection entirely while silently not crashing the process (the
    library logs the error and returns no detections for that frame).
    Correctness beats the synthetic benchmark's speed number here; pass
    `detector_providers=("CoreMLExecutionProvider", "CPUExecutionProvider")`
    explicitly if a caller wants to opt back in for content known not to
    trigger this.

    OCR is `cct-xs-v2`, not the larger `cct-s-v2`: on 81 hand-labelled
    Gujarat plates the small model read 30 exactly where the larger one
    read 7 (evidence/ANPR-ACCURACY.md), and it is about six times faster.
    """

    def __init__(
        self,
        *,
        detector_model: str = "yolo-v9-t-640-license-plate-end2end",
        ocr_model: str = "cct-xs-v2-global-model",
        detector_providers: Sequence[str] = ("CPUExecutionProvider",),
        ocr_providers: Sequence[str] = ("CPUExecutionProvider",),
        detector_conf_thresh: float = 0.4,
    ) -> None:
        self._alpr = ALPR(
            detector_model=detector_model,
            detector_providers=list(detector_providers),
            detector_conf_thresh=detector_conf_thresh,
            ocr_model=ocr_model,
            ocr_providers=list(ocr_providers),
        )

    def read(self, image: np.ndarray) -> list[PlateCandidate]:
        """Detect and read every plate in `image` (a full frame or a vehicle
        ROI crop — both work; cropping to the vehicle first is cheaper and
        is what the pipeline in analytics/pipeline.py does)."""
        height, width = image.shape[:2]
        candidates = []
        for detection in self._alpr.detector.predict(image):
            box = detection.bounding_box
            # The detector's box hugs the plate tightly enough to clip the
            # last character on small plates; OCR reads a padded crop.
            pad_x = (box.x2 - box.x1) * PLATE_PAD_X
            pad_y = (box.y2 - box.y1) * PLATE_PAD_Y
            x1, y1 = max(0, int(box.x1 - pad_x)), max(0, int(box.y1 - pad_y))
            x2, y2 = min(width, int(box.x2 + pad_x)), min(height, int(box.y2 + pad_y))
            if x2 <= x1 or y2 <= y1:
                continue
            ocr = self._alpr.ocr.predict(image[y1:y2, x1:x2])
            if ocr is None:
                continue
            candidates.append(
                PlateCandidate(
                    text=ocr.text,
                    char_confidences=tuple(ocr.confidence),
                    bbox_xyxy=(float(box.x1), float(box.y1), float(box.x2), float(box.y2)),
                )
            )
        return candidates
