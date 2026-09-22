"""YOLO output decoding — pure numpy math, no model weights needed.

Constructs synthetic `(1, 4+num_classes, num_anchors)` tensors directly,
mirroring how a real YOLOv8/v11 ONNX export shapes its output, so this stage
is tested without downloading or running the actual model.
"""

from __future__ import annotations

import numpy as np
import pytest

from edge_agent.analytics.vehicle_detector import VEHICLE_CLASSES, decode_yolo_output

NUM_CLASSES = 80


def _synthetic_output(
    detections: list[tuple[float, float, float, float, int, float]],
) -> np.ndarray:
    """Build a raw YOLO tensor from (cx, cy, w, h, class_id, score) tuples,
    in *letterboxed* (already-padded, already-scaled) coordinates."""
    num_anchors = len(detections)
    output = np.zeros((1, 4 + NUM_CLASSES, num_anchors), dtype=np.float32)
    for i, (cx, cy, w, h, class_id, score) in enumerate(detections):
        output[0, 0, i] = cx
        output[0, 1, i] = cy
        output[0, 2, i] = w
        output[0, 3, i] = h
        output[0, 4 + class_id, i] = score
    return output


def test_decodes_a_single_confident_car_detection() -> None:
    raw = _synthetic_output([(320.0, 320.0, 100.0, 60.0, 2, 0.9)])  # class 2 = car

    detections = decode_yolo_output(raw, letterbox_result_scale=1.0, letterbox_pad=(0.0, 0.0))

    assert len(detections) == 1
    assert detections[0].vehicle_class == "car"
    assert detections[0].confidence == pytest.approx(0.9)
    x1, y1, x2, y2 = detections[0].bbox_xyxy
    assert (x1, y1, x2, y2) == (270.0, 290.0, 370.0, 350.0)


def test_non_vehicle_classes_are_filtered_out() -> None:
    """A person (class 0) or a traffic light must never reach the tracker —
    this is a vehicle-centric pipeline by design (see 00-SOLUTION-PLAN.md
    section 9: no face recognition, vehicle-centric analytics only)."""
    raw = _synthetic_output([(320.0, 320.0, 100.0, 60.0, 0, 0.95)])  # class 0 = person

    detections = decode_yolo_output(raw, letterbox_result_scale=1.0, letterbox_pad=(0.0, 0.0))

    assert detections == []


def test_low_confidence_detections_are_dropped() -> None:
    raw = _synthetic_output([(320.0, 320.0, 100.0, 60.0, 2, 0.1)])

    detections = decode_yolo_output(
        raw, letterbox_result_scale=1.0, letterbox_pad=(0.0, 0.0), conf_thresh=0.4
    )

    assert detections == []


def test_nms_collapses_overlapping_duplicate_boxes() -> None:
    """Anchor-based detectors routinely fire multiple overlapping boxes for
    one real vehicle; NMS must collapse them to one."""
    raw = _synthetic_output(
        [
            (320.0, 320.0, 100.0, 60.0, 2, 0.90),
            (322.0, 318.0, 98.0, 62.0, 2, 0.85),  # near-duplicate of the above
            (100.0, 100.0, 40.0, 40.0, 2, 0.80),  # a genuinely separate vehicle
        ]
    )

    detections = decode_yolo_output(raw, letterbox_result_scale=1.0, letterbox_pad=(0.0, 0.0))

    assert len(detections) == 2
    assert detections[0].confidence == pytest.approx(0.90)  # the higher-confidence duplicate wins


def test_letterbox_padding_and_scale_are_undone() -> None:
    """A box detected in the padded/resized frame must map back to the
    original image's pixel coordinates."""
    # Original image was scaled by 0.5 and padded by 20px on each axis before
    # detection, so a box at (cx=340, cy=220) in letterboxed space is really
    # at ((340-20)/0.5, (220-20)/0.5) = (640, 400) in the original image.
    raw = _synthetic_output([(340.0, 220.0, 40.0, 40.0, 2, 0.9)])

    detections = decode_yolo_output(raw, letterbox_result_scale=0.5, letterbox_pad=(20.0, 20.0))

    x1, y1, x2, y2 = detections[0].bbox_xyxy
    center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
    assert abs(center_x - 640.0) < 1e-3
    assert abs(center_y - 400.0) < 1e-3


def test_empty_frame_produces_no_detections() -> None:
    raw = np.zeros((1, 4 + NUM_CLASSES, 100), dtype=np.float32)

    assert decode_yolo_output(raw, letterbox_result_scale=1.0, letterbox_pad=(0.0, 0.0)) == []


def test_bbox_xywh_matches_xyxy() -> None:
    raw = _synthetic_output([(320.0, 320.0, 100.0, 60.0, 2, 0.9)])
    detection = decode_yolo_output(raw, letterbox_result_scale=1.0, letterbox_pad=(0.0, 0.0))[0]

    x, y, w, h = detection.bbox_xywh
    x1, y1, x2, y2 = detection.bbox_xyxy
    assert (x, y, w, h) == (x1, y1, x2 - x1, y2 - y1)


def test_all_documented_vehicle_classes_are_recognised() -> None:
    for class_id, name in VEHICLE_CLASSES.items():
        raw = _synthetic_output([(320.0, 320.0, 100.0, 60.0, class_id, 0.9)])
        detections = decode_yolo_output(raw, letterbox_result_scale=1.0, letterbox_pad=(0.0, 0.0))
        assert detections[0].vehicle_class == name
