"""Tests for the HSV-heuristic vehicle colour classifier — pure pixel math,
no model weights, no ONNX Runtime."""

from __future__ import annotations

import numpy as np

from edge_agent.analytics.colour import classify_vehicle_colour


def _solid(bgr: tuple[int, int, int], size: int = 100) -> np.ndarray:
    return np.full((size, size, 3), bgr, dtype=np.uint8)


def test_classifies_white() -> None:
    assert classify_vehicle_colour(_solid((255, 255, 255))) == "white"


def test_classifies_black() -> None:
    assert classify_vehicle_colour(_solid((0, 0, 0))) == "black"


def test_classifies_silver_gray() -> None:
    assert classify_vehicle_colour(_solid((180, 180, 180))) == "silver"


def test_classifies_a_dark_gray_as_gray_not_black() -> None:
    assert classify_vehicle_colour(_solid((90, 90, 90))) == "gray"


def test_classifies_red() -> None:
    assert classify_vehicle_colour(_solid((0, 0, 255))) == "red"  # BGR


def test_classifies_blue() -> None:
    assert classify_vehicle_colour(_solid((255, 0, 0))) == "blue"  # BGR


def test_classifies_green() -> None:
    assert classify_vehicle_colour(_solid((0, 255, 0))) == "green"  # BGR


def test_classifies_yellow() -> None:
    assert classify_vehicle_colour(_solid((0, 255, 255))) == "yellow"  # BGR


def test_returns_none_for_an_empty_crop() -> None:
    assert classify_vehicle_colour(np.zeros((0, 0, 3), dtype=np.uint8)) is None


def test_returns_none_for_a_crop_too_small_to_classify() -> None:
    assert classify_vehicle_colour(np.zeros((3, 3, 3), dtype=np.uint8)) is None


def test_uses_the_central_region_ignoring_a_noisy_border() -> None:
    """A crop with a noisy/background-coloured border but a solid centre
    (the realistic shape of a vehicle bounding box, which often includes a
    sliver of road/shadow at the edges) should classify by the centre."""
    crop = np.full((100, 100, 3), (0, 0, 255), dtype=np.uint8)  # red centre
    crop[:10, :] = (0, 255, 0)  # green border strip — outside the central 60%
    crop[-10:, :] = (0, 255, 0)
    crop[:, :10] = (0, 255, 0)
    crop[:, -10:] = (0, 255, 0)

    assert classify_vehicle_colour(crop) == "red"
