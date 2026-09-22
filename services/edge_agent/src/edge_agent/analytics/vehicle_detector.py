"""Vehicle detection — ONNX Runtime, YOLO11n weights (AGPL-3.0, documented
and accepted; see 02-ANPR-PIPELINE.md section 8 for the licence position and
the Apache-only migration path).

The raw-output decode (`decode_yolo_output`) is a pure function with no
ONNX Runtime dependency, so it is unit tested against constructed tensors
rather than the real model — the same hermetic-testing pattern used for
RtspCapture's fake VideoSource.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from edge_agent.analytics.preprocess import letterbox

__all__ = ["VehicleDetection", "VehicleDetector", "decode_yolo_output"]

# COCO class ids relevant to vehicle-centric ANPR. Everything else (person,
# traffic light, etc.) is discarded before it ever reaches the tracker.
VEHICLE_CLASSES: dict[int, str] = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


@dataclass(frozen=True, slots=True)
class VehicleDetection:
    bbox_xyxy: tuple[float, float, float, float]
    vehicle_class: str
    confidence: float

    @property
    def bbox_xywh(self) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = self.bbox_xyxy
        return (x1, y1, x2 - x1, y2 - y1)


def decode_yolo_output(
    raw_output: np.ndarray,
    letterbox_result_scale: float,
    letterbox_pad: tuple[float, float],
    *,
    conf_thresh: float = 0.4,
    iou_thresh: float = 0.45,
    class_filter: dict[int, str] = VEHICLE_CLASSES,
) -> list[VehicleDetection]:
    """Decode a YOLOv8/v11-style `(1, 4+num_classes, num_anchors)` tensor.

    Pure function: no ONNX Runtime, no file I/O. `letterbox_result_scale`/
    `letterbox_pad` undo the preprocessing so boxes land in original-image
    pixel coordinates.
    """
    predictions = raw_output[0].T  # (num_anchors, 4 + num_classes)
    boxes_cxcywh = predictions[:, :4]
    class_scores = predictions[:, 4:]

    class_ids = np.argmax(class_scores, axis=1)
    confidences = class_scores[np.arange(len(class_scores)), class_ids]

    keep_mask = confidences >= conf_thresh
    if class_filter:
        keep_mask &= np.isin(class_ids, list(class_filter.keys()))
    if not np.any(keep_mask):
        return []

    boxes_cxcywh = boxes_cxcywh[keep_mask]
    class_ids = class_ids[keep_mask]
    confidences = confidences[keep_mask]

    cx, cy, w, h = boxes_cxcywh.T
    boxes_xyxy = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)

    pad_x, pad_y = letterbox_pad
    boxes_xyxy[:, [0, 2]] -= pad_x
    boxes_xyxy[:, [1, 3]] -= pad_y
    boxes_xyxy /= letterbox_result_scale

    nms_indices = cv2.dnn.NMSBoxes(
        boxes_xyxy.tolist(), confidences.tolist(), conf_thresh, iou_thresh
    )
    if len(nms_indices) == 0:
        return []
    kept_indices = np.array(nms_indices).flatten()

    return [
        VehicleDetection(
            bbox_xyxy=(
                float(boxes_xyxy[i, 0]),
                float(boxes_xyxy[i, 1]),
                float(boxes_xyxy[i, 2]),
                float(boxes_xyxy[i, 3]),
            ),
            vehicle_class=class_filter.get(int(class_ids[i]), str(class_ids[i])),
            confidence=float(confidences[i]),
        )
        for i in kept_indices
    ]


class VehicleDetector:
    """ONNX Runtime wrapper. CoreML EP on Apple Silicon with a CPU fallback —
    measured 5-8x faster than CPU-only for this model family (see
    02-ANPR-PIPELINE.md section 3)."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        input_size: int = 640,
        conf_thresh: float = 0.4,
        iou_thresh: float = 0.45,
        providers: Sequence[str] = ("CoreMLExecutionProvider", "CPUExecutionProvider"),
    ) -> None:
        self._session = ort.InferenceSession(str(model_path), providers=list(providers))
        self._input_name = self._session.get_inputs()[0].name
        self._input_size = input_size
        self._conf_thresh = conf_thresh
        self._iou_thresh = iou_thresh

    def detect(self, frame: np.ndarray) -> list[VehicleDetection]:
        lb = letterbox(frame, self._input_size)
        blob = cv2.cvtColor(lb.image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis, ...]  # HWC -> NCHW

        raw = self._session.run(None, {self._input_name: blob})[0]
        return decode_yolo_output(
            raw,
            lb.scale,
            (lb.pad_x, lb.pad_y),
            conf_thresh=self._conf_thresh,
            iou_thresh=self._iou_thresh,
        )

    @property
    def providers_in_use(self) -> list[str]:
        providers: list[str] = self._session.get_providers()
        return providers
