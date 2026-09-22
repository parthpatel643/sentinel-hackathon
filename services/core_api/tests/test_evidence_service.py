"""Evidence-clip sealing tests — the blocking file/ffmpeg half
(_seal_from_segments) runs entirely synchronously and needs no live
MediaMTX/DB, so it's tested directly against real ffmpeg-generated fixture
segments rather than mocked."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from core_api.evidence.service import _seal_from_segments

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def _make_test_clip(path: Path, duration_s: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=320x240:rate=10:duration={duration_s}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_seals_a_single_segment_and_hashes_the_actual_bytes(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "dev" / "dev-cam-01"
    recordings_dir.mkdir(parents=True)
    segment = recordings_dir / "2026-01-01_00-00-00-000000.mp4"
    _make_test_clip(segment)

    clip_id = uuid.uuid4()
    result = _seal_from_segments(recordings_dir, set(), 0.0, tmp_path / "sealed", clip_id)

    assert result.error is None
    assert result.file_path is not None
    assert result.file_path.is_file()
    assert result.sha256 == hashlib.sha256(result.file_path.read_bytes()).hexdigest()
    assert result.duration_s is not None
    assert result.duration_s == pytest.approx(1.0, abs=0.3)


def test_concatenates_multiple_segments_into_one_longer_clip(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "dev" / "dev-cam-02"
    recordings_dir.mkdir(parents=True)
    first = recordings_dir / "2026-01-01_00-00-00-000000.mp4"
    second = recordings_dir / "2026-01-01_00-00-01-000000.mp4"
    _make_test_clip(first, duration_s=1.0)
    _make_test_clip(second, duration_s=1.0)

    result = _seal_from_segments(recordings_dir, set(), 0.0, tmp_path / "sealed", uuid.uuid4())

    assert result.error is None
    assert result.duration_s is not None
    # Two ~1s segments concatenated should be roughly 2s, not 1s — proof the
    # seal actually combined both files rather than silently keeping one.
    assert result.duration_s > 1.5


def test_reports_an_error_when_no_segments_exist(tmp_path: Path) -> None:
    recordings_dir = tmp_path / "dev" / "dev-cam-03"
    recordings_dir.mkdir(parents=True)

    result = _seal_from_segments(recordings_dir, set(), 0.0, tmp_path / "sealed", uuid.uuid4())

    assert result.error is not None
    assert result.file_path is None


def test_reports_an_error_when_the_recordings_directory_never_existed(tmp_path: Path) -> None:
    missing_dir = tmp_path / "dev" / "dev-cam-nonexistent"

    result = _seal_from_segments(missing_dir, set(), 0.0, tmp_path / "sealed", uuid.uuid4())

    assert result.error is not None
    assert "recordings directory" in result.error.lower()


def test_existing_segments_from_before_the_window_are_excluded(tmp_path: Path) -> None:
    """A camera that was already recording for an earlier alert must not
    have its old segments swept into a new, unrelated seal."""
    recordings_dir = tmp_path / "dev" / "dev-cam-04"
    recordings_dir.mkdir(parents=True)
    stale = recordings_dir / "stale.mp4"
    _make_test_clip(stale, duration_s=1.0)

    # Mark the stale segment as "already existed" before this seal window
    # started, with an mtime safely in the past.
    old_time = time.time() - 3600
    os.utime(stale, (old_time, old_time))

    result = _seal_from_segments(
        recordings_dir, {stale}, time.time(), tmp_path / "sealed", uuid.uuid4()
    )

    assert result.error is not None
    assert result.file_path is None
