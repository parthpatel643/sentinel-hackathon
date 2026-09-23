"""Tests for the model-free half of face blurring — `blur_regions` and
`ensure_model_downloaded`'s idempotent-skip behaviour. `detect_faces`/
`blur_faces` themselves call the real YuNet DNN model and are
deliberately not unit-tested here, matching the boundary
`test_vehicle_detector.py` already draws around the ONNX-calling half of
that pipeline stage — this module tests the pure logic around it instead.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np

from edge_agent.analytics.face_blur import blur_regions, ensure_model_downloaded


def test_blur_regions_leaves_pixels_outside_every_box_untouched() -> None:
    image = np.full((100, 100, 3), 200, dtype=np.uint8)

    blurred = blur_regions(image, boxes=[(10, 10, 20, 20)])

    assert np.array_equal(blurred[0:10, :], image[0:10, :])
    assert np.array_equal(blurred[:, 0:10], image[:, 0:10])
    assert np.array_equal(blurred[40:, :], image[40:, :])


def test_blur_regions_genuinely_changes_pixels_inside_the_box() -> None:
    """A flat-colour box can't show a *Gaussian* blur changing anything (it
    has no variance to smooth), so this uses a half-and-half box: blurring
    must visibly soften the hard edge between the two halves."""
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[10:30, 10:20] = 255  # left half of the box white, right half black

    blurred = blur_regions(image, boxes=[(10, 10, 20, 20)])

    assert not np.array_equal(blurred[10:30, 10:30], image[10:30, 10:30])


def test_blur_regions_does_not_mutate_the_input_image() -> None:
    image = np.zeros((50, 50, 3), dtype=np.uint8)
    image[5:25, 5:25] = 255
    original = image.copy()

    blur_regions(image, boxes=[(5, 5, 20, 20)])

    assert np.array_equal(image, original)


def test_blur_regions_skips_a_box_that_is_entirely_out_of_bounds() -> None:
    """No IndexError/crash for a box a detector could plausibly hand back
    right at a frame edge."""
    image = np.zeros((50, 50, 3), dtype=np.uint8)

    blurred = blur_regions(image, boxes=[(1000, 1000, 20, 20)])

    assert blurred.shape == image.shape


def test_ensure_model_downloaded_skips_the_download_if_already_cached(tmp_path: Path) -> None:
    model_path = tmp_path / "face_detection_yunet_2023mar.onnx"
    model_path.write_bytes(b"fake-onnx-weights")

    with patch("edge_agent.analytics.face_blur.urllib.request.urlretrieve") as mock_download:
        result = ensure_model_downloaded(model_path)

    mock_download.assert_not_called()
    assert result == model_path


def test_ensure_model_downloaded_downloads_when_missing(tmp_path: Path) -> None:
    model_path = tmp_path / "nested" / "face_detection_yunet_2023mar.onnx"

    def _fake_urlretrieve(url: str, filename: Path) -> None:
        Path(filename).write_bytes(b"fake-onnx-weights")

    with patch(
        "edge_agent.analytics.face_blur.urllib.request.urlretrieve", side_effect=_fake_urlretrieve
    ) as mock_download:
        result = ensure_model_downloaded(model_path)

    mock_download.assert_called_once()
    assert result == model_path
    assert model_path.exists()
