"""Vehicle colour classification — M13 secondary analytics: docs/05-
DELIVERY-PLAN.md's "vehicle class/colour/coarse-make." Deliberately a
lightweight HSV-histogram heuristic, not a trained classifier — the
decision record (docs/00-SOLUTION-PLAN.md §9) explicitly puts the time
freed by excluding face recognition into vehicle *attributes*, and a
real, if coarse, colour signal is achievable without a second model or
GPU budget; a trained fine-grained colour/make classifier is a
documented next step, not silently claimed here.

Coarse-make (manufacturer/model) is **not** attempted at all — genuine
make/model recognition needs a purpose-trained classifier on a large
labelled dataset, categorically different from a pixel-statistics
heuristic, and is honestly out of scope for this build.
"""

from __future__ import annotations

import cv2
import numpy as np

__all__ = ["classify_vehicle_colour"]

# (name, hue range in OpenCV's 0-179 H scale, min saturation, min value) —
# order matters: achromatic checks (white/black/gray) run first since a
# desaturated pixel's hue is meaningless noise, not a real colour signal.
_HUE_BANDS: list[tuple[str, tuple[int, int]]] = [
    ("red", (0, 10)),
    ("orange", (10, 25)),
    ("yellow", (25, 35)),
    ("green", (35, 85)),
    ("cyan", (85, 100)),
    ("blue", (100, 130)),
    ("purple", (130, 150)),
    ("red", (150, 180)),  # red wraps around the hue circle
]


def classify_vehicle_colour(crop: np.ndarray) -> str | None:
    """Returns a coarse named colour (white/black/silver/gray/red/orange/
    yellow/green/cyan/blue/purple) for a vehicle bounding-box crop, or
    `None` if the crop is empty or too small to classify meaningfully.

    Method: convert to HSV, take the median H/S/V over the crop's central
    region (avoiding the crop's edges, which are more likely to be
    background/road rather than vehicle body), then bucket by saturation/
    value first (achromatic: white, black, silver/gray) and only consult
    hue for genuinely saturated pixels."""
    if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8:
        return None

    height, width = crop.shape[:2]
    # Central 60% of the crop — the vehicle body's paint, not the tyres/
    # shadow near the bottom edge or background sliver near the top.
    y0, y1 = int(height * 0.2), int(height * 0.8)
    x0, x1 = int(width * 0.2), int(width * 0.8)
    region = crop[y0:y1, x0:x1]
    if region.size == 0:
        return None

    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    h = float(np.median(hsv[:, :, 0]))
    s = float(np.median(hsv[:, :, 1]))
    v = float(np.median(hsv[:, :, 2]))

    if v < 50:
        return "black"
    if s < 30:
        return "white" if v > 180 else ("silver" if v > 120 else "gray")

    for name, (lo, hi) in _HUE_BANDS:
        if lo <= h < hi:
            return name
    return None
