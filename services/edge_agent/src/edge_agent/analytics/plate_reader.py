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

__all__ = ["FastAlprPlateReader", "PlateCandidate"]


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
    """Default execution-provider policy, measured on Apple Silicon (base M2):

    - Plate DETECTOR on CoreML EP: 5-8.6x faster than CPU for this model
      family (YOLOv9).
    - OCR on CPU EP, explicitly pinned: CoreML makes the CCT OCR models
      *slower* (attention-op partitioning overhead dominates a sub-2ms
      model) — the opposite of the detector, and the opposite of what
      fast-plate-ocr's own docs suggest for the *legacy* CNN models. Do not
      trust automatic provider selection for this stage.
    """

    def __init__(
        self,
        *,
        detector_model: str = "yolo-v9-t-640-license-plate-end2end",
        ocr_model: str = "cct-s-v2-global-model",
        detector_providers: Sequence[str] = ("CoreMLExecutionProvider", "CPUExecutionProvider"),
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
        results = self._alpr.predict(image)
        candidates = []
        for r in results:
            if r.ocr is None:
                continue
            box = r.detection.bounding_box
            candidates.append(
                PlateCandidate(
                    text=r.ocr.text,
                    char_confidences=tuple(r.ocr.confidence),
                    bbox_xyxy=(float(box.x1), float(box.y1), float(box.x2), float(box.y2)),
                )
            )
        return candidates
