"""Which relay path a camera's recordings live under.

Sealing used to assume every camera sat under `dev/<id>` — the synthetic
grid's namespace — so sealing a clip for a government camera failed with
"No recordings directory for camera at data/recordings/dev/cam06". The
camera was streaming fine; the recorder was looking in the wrong place.

These tests are deliberately infrastructure-free: the resolution is pure
logic over a camera's RTSP profile, and that is exactly the part that was
wrong.
"""

from __future__ import annotations

import pytest

from core_api.db.models import Camera, StreamProfile
from core_api.evidence.service import _recording_dir_for_path, relay_path_for_camera
from sentinel_core.config import Settings


@pytest.fixture
def settings(tmp_path: object) -> Settings:
    return Settings(
        relay_rtsp_url="rtsp://localhost:8554",
        relay_api_url="http://localhost:9997",
        recordings_dir="data/recordings",
    )


def _camera(camera_id: str, rtsp_url: str | None) -> Camera:
    camera = Camera(camera_id=camera_id, name=camera_id, driver_id="rtsp")
    camera.profiles = (
        [StreamProfile(camera_id=camera_id, protocol="rtsp", url=rtsp_url)] if rtsp_url else []
    )
    return camera


def test_a_synthetic_camera_keeps_its_dev_path(settings: Settings) -> None:
    """The synthetic grid publishes straight into the relay, so its path is
    whatever it published to — not a derived one."""
    camera = _camera("dev-cam-01", "rtsp://127.0.0.1:8554/dev/dev-cam-01")
    assert relay_path_for_camera(camera, settings) == "dev/dev-cam-01"


def test_a_government_camera_resolves_to_its_ext_path(settings: Settings) -> None:
    """This is the case that was broken: an external camera is republished
    under ext/<id>, and sealing looked under dev/<id>."""
    camera = _camera("cam06", "rtsp://user:pass@103.250.160.189:8554/stream/cam06")
    assert relay_path_for_camera(camera, settings) == "ext/cam06"


def test_a_camera_with_no_rtsp_profile_still_resolves(settings: Settings) -> None:
    """Falling back to the ext path keeps sealing's failure a clear "no
    recordings yet" rather than a crash resolving the path."""
    assert relay_path_for_camera(_camera("cam99", None), settings) == "ext/cam99"


def test_the_recording_directory_mirrors_the_relay_path(settings: Settings) -> None:
    """mediamtx.yml records to /recordings/%path/, bind-mounted at
    recordings_dir — so the directory has to mirror the path exactly."""
    assert str(_recording_dir_for_path(settings, "ext/cam06")) == "data/recordings/ext/cam06"
    assert (
        str(_recording_dir_for_path(settings, "dev/dev-cam-01"))
        == "data/recordings/dev/dev-cam-01"
    )


def test_localhost_and_loopback_are_the_same_relay(settings: Settings) -> None:
    """A camera registered against 127.0.0.1 must not be treated as external
    just because the relay is configured as `localhost`."""
    for host in ("localhost", "127.0.0.1"):
        camera = _camera("dev-cam-02", f"rtsp://{host}:8554/dev/dev-cam-02")
        assert relay_path_for_camera(camera, settings) == "dev/dev-cam-02"
