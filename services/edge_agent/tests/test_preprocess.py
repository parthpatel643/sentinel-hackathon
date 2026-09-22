"""Letterbox resize/pad math — pure, no ONNX Runtime, no camera required."""

from __future__ import annotations

import numpy as np

from edge_agent.analytics.preprocess import letterbox, scale_boxes_to_original


def test_letterbox_pads_a_wide_image_top_and_bottom() -> None:
    image = np.zeros((480, 640, 3), dtype=np.uint8)  # wider than tall

    result = letterbox(image, target_size=640)

    assert result.image.shape == (640, 640, 3)
    assert result.pad_y > 0
    assert result.pad_x == 0


def test_letterbox_pads_a_tall_image_left_and_right() -> None:
    image = np.zeros((640, 320, 3), dtype=np.uint8)  # taller than wide

    result = letterbox(image, target_size=640)

    assert result.image.shape == (640, 640, 3)
    assert result.pad_x > 0
    assert result.pad_y == 0


def test_letterbox_preserves_aspect_ratio() -> None:
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)  # 16:9, mixed grid reality

    result = letterbox(image, target_size=640)

    assert abs(result.scale - 640 / 1920) < 1e-9


def test_scale_boxes_to_original_undoes_letterboxing_exactly() -> None:
    """A box drawn in the padded/resized frame must map back to the same
    pixel location it started from in the original image."""
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    result = letterbox(image, target_size=640)

    # A box that, in original coordinates, was exactly [100, 50, 200, 150].
    original_box = np.array([[100.0, 50.0, 200.0, 150.0]])
    letterboxed_box = original_box * result.scale
    letterboxed_box[:, [0, 2]] += result.pad_x
    letterboxed_box[:, [1, 3]] += result.pad_y

    recovered = scale_boxes_to_original(letterboxed_box, result)

    assert np.allclose(recovered, original_box, atol=0.5)


def test_letterbox_fill_colour_is_neutral_grey_not_black() -> None:
    """Pure black padding can bias a detector trained with grey letterbox
    padding (the YOLO convention) toward false detections at the border."""
    image = np.zeros((100, 640, 3), dtype=np.uint8)
    result = letterbox(image, target_size=640)

    corner_pixel = result.image[0, 0]
    assert tuple(int(c) for c in corner_pixel) == (114, 114, 114)
