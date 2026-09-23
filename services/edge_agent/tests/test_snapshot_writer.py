"""Tests for SnapshotWriter — dual-write (blurred + original) and the
snapshot_uri it hands back. Uses a fake `blur_fn` so no real face-detector
model is needed (see test_face_blur.py's docstring for the same reasoning).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from edge_agent.analytics.snapshot_writer import SnapshotWriter


def _fake_blur(image: np.ndarray) -> np.ndarray:
    """A deterministic, obviously-different stand-in for a real blur —
    inverts every pixel, so "is this the blurred file or the original"
    is a trivial pixel comparison in tests."""
    return 255 - image


def test_write_returns_a_snapshot_scheme_uri_keyed_by_event_id(tmp_path: Path) -> None:
    writer = SnapshotWriter(
        blurred_dir=tmp_path / "blurred", originals_dir=tmp_path / "originals", blur_fn=_fake_blur
    )
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    uri = writer.write("evt-001", frame)

    assert uri == "snapshot://evt-001"


def test_write_saves_the_blurred_version_to_the_blurred_dir(tmp_path: Path) -> None:
    writer = SnapshotWriter(
        blurred_dir=tmp_path / "blurred", originals_dir=tmp_path / "originals", blur_fn=_fake_blur
    )
    frame = np.full((10, 10, 3), 50, dtype=np.uint8)

    writer.write("evt-002", frame)

    saved = cv2.imread(str(tmp_path / "blurred" / "evt-002.jpg"))
    assert saved is not None
    assert not np.array_equal(saved, frame)  # inverted by the fake blur, not the raw frame


def test_write_saves_the_true_original_unblurred_to_the_originals_dir(tmp_path: Path) -> None:
    writer = SnapshotWriter(
        blurred_dir=tmp_path / "blurred", originals_dir=tmp_path / "originals", blur_fn=_fake_blur
    )
    frame = np.full((10, 10, 3), 50, dtype=np.uint8)

    writer.write("evt-003", frame)

    saved = cv2.imread(str(tmp_path / "originals" / "evt-003.jpg"))
    assert saved is not None
    assert np.array_equal(saved, frame)


def test_write_creates_both_directories_if_they_do_not_exist(tmp_path: Path) -> None:
    blurred_dir = tmp_path / "does" / "not" / "exist" / "blurred"
    originals_dir = tmp_path / "also" / "missing" / "originals"

    SnapshotWriter(blurred_dir=blurred_dir, originals_dir=originals_dir, blur_fn=_fake_blur)

    assert blurred_dir.is_dir()
    assert originals_dir.is_dir()


def test_write_returns_empty_string_and_writes_nothing_if_blurring_fails(tmp_path: Path) -> None:
    """A face-detector failure must never fall back to silently saving the
    unblurred frame as if it were the safe default — no snapshot at all is
    the correct failure mode."""

    def _broken_blur(image: np.ndarray) -> np.ndarray:
        raise RuntimeError("simulated model failure")

    writer = SnapshotWriter(
        blurred_dir=tmp_path / "blurred",
        originals_dir=tmp_path / "originals",
        blur_fn=_broken_blur,
    )
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    uri = writer.write("evt-004", frame)

    assert uri == ""
    assert not (tmp_path / "blurred" / "evt-004.jpg").exists()
    assert not (tmp_path / "originals" / "evt-004.jpg").exists()


@pytest.fixture(autouse=True)
def _no_real_model_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt-and-braces: fail loudly if anything in this file accidentally
    reaches the real network-downloading path instead of using the fake
    blur_fn every test above passes explicitly."""

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("test_snapshot_writer.py must never touch the real model download")

    monkeypatch.setattr("edge_agent.analytics.face_blur.urllib.request.urlretrieve", _boom)
