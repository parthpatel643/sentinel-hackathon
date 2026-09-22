"""Letterbox preprocessing shared by the vehicle detector.

Kept separate from the detector class so the pure-math resize/pad logic (and
its inverse, mapping boxes back to the original image) can be unit tested
without an ONNX Runtime session.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

__all__ = ["LetterboxResult", "letterbox", "scale_boxes_to_original"]


@dataclass(frozen=True, slots=True)
class LetterboxResult:
    image: np.ndarray
    scale: float
    """Uniform scale factor applied to the original image."""
    pad_x: float
    pad_y: float
    """Padding added on each side, in the *resized* (target) coordinate space."""


def letterbox(image: np.ndarray, target_size: int = 640) -> LetterboxResult:
    """Resize preserving aspect ratio, padding to a square target with grey.

    A fixed-shape inference batch across every camera does not work — cameras
    differ in resolution (docs/01-ARCHITECTURE.md section 4.3) — so every
    detector call letterboxes independently rather than assuming a uniform
    input shape upstream.
    """
    height, width = image.shape[:2]
    scale = min(target_size / height, target_size / width)
    new_w, new_h = round(width * scale), round(height * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_x = (target_size - new_w) / 2
    pad_y = (target_size - new_h) / 2
    top, bottom = round(pad_y - 0.1), round(pad_y + 0.1)
    left, right = round(pad_x - 0.1), round(pad_x + 0.1)

    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    return LetterboxResult(image=padded, scale=scale, pad_x=pad_x, pad_y=pad_y)


def scale_boxes_to_original(boxes_xyxy: np.ndarray, result: LetterboxResult) -> np.ndarray:
    """Undo letterboxing: map boxes from the padded/resized space back to the
    original image's pixel coordinates."""
    boxes = boxes_xyxy.copy()
    boxes[:, [0, 2]] -= result.pad_x
    boxes[:, [1, 3]] -= result.pad_y
    boxes /= result.scale
    return boxes
