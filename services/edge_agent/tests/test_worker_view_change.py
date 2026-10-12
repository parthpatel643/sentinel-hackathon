"""How the worker reports a camera whose view changed."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from edge_agent.analytics.tamper import TamperDetector
from edge_agent.analytics.view_monitor import ViewChange, ViewMonitor
from edge_agent.worker import _camera_condition, _monitors_view, _report_view_change
from sentinel_core.clock import Frame, FrameTiming
from sentinel_core.config import Settings
from sentinel_core.schemas import CameraDescriptor

PROCESSED_AT = datetime(2026, 10, 12, 5, 0, tzinfo=UTC)
SCENE_TIME = datetime(2026, 8, 8, 15, 40, 33, tzinfo=UTC)


def _frame() -> Frame[np.ndarray]:
    timing = FrameTiming(
        camera_id="cam30",
        pts_ms=120_000.0,
        seq=0,
        stream_epoch=PROCESSED_AT,
        observed_at=PROCESSED_AT,
        delta_ms=40.0,
        is_gap=False,
        is_discontinuity=False,
    )
    return Frame(timing=timing, image=np.zeros((4, 4, 3), dtype=np.uint8), width=4, height=4)


def _change(kind: str) -> ViewChange:
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    return ViewChange(
        kind=kind,  # type: ignore[arg-type]
        pts_ms=120_000.0,
        shift_pct=12.3 if kind == "shifted" else None,
        rotation_deg=0.1 if kind == "shifted" else None,
        scale=1.0 if kind == "shifted" else None,
        match_ratio=0.3,
        reference=image,
        current=image,
    )


class _Pipeline:
    def camera_time_of(self, frame: Frame[np.ndarray]) -> datetime | None:
        return SCENE_TIME


class _Writer:
    def __init__(self, directory: Path, fail: bool = False) -> None:
        self.directory = directory
        self.fail = fail
        self.written: list[str] = []

    def write(self, event_id: str, frame_image: np.ndarray) -> str:
        if self.fail:
            return ""
        (self.directory / f"{event_id}.jpg").write_bytes(b"\xff\xd8\xffjpeg")
        self.written.append(event_id)
        return f"snapshot://{event_id}"


async def _report(
    kind: str, tmp_path: Path, *, upload: bool = False, fail_snapshots: bool = False
) -> tuple[list[httpx.Request], _Writer]:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={})

    writer = _Writer(tmp_path, fail=fail_snapshots)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://api"
    ) as client:
        await _report_view_change(
            client,
            "cam30",
            _change(kind),
            _frame(),
            _Pipeline(),  # type: ignore[arg-type]
            writer,  # type: ignore[arg-type]
            settings=Settings(snapshots_dir=str(tmp_path)),
            upload_snapshots=upload,
        )
    return requests, writer


def _body(request: httpx.Request) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(request.content)
    return body


async def test_a_moved_camera_is_reported_with_before_and_after_frames(tmp_path: Path) -> None:
    requests, writer = await _report("shifted", tmp_path)

    assert [r.url.path for r in requests] == ["/api/v1/camera-events"]
    body = _body(requests[0])
    assert body["kind"] == "view_shifted"
    assert body["shift_pct"] == 12.3
    assert body["camera_time"] == SCENE_TIME.isoformat(), "the camera's own clock"
    assert body["observed_at"] == PROCESSED_AT.isoformat()
    assert body["has_snapshots"] is True
    assert writer.written == [f"{body['event_id']}-before", f"{body['event_id']}-after"]


async def test_an_unrecognised_view_is_its_own_kind(tmp_path: Path) -> None:
    requests, _ = await _report("unrecognised", tmp_path)
    body = _body(requests[0])
    assert body["kind"] == "view_unrecognised"
    assert body["shift_pct"] is None


async def test_a_worker_on_another_machine_uploads_both_frames(tmp_path: Path) -> None:
    requests, _ = await _report("shifted", tmp_path, upload=True)
    event_id = _body(requests[0])["event_id"]
    assert [r.url.path for r in requests[1:]] == [
        f"/api/v1/camera-events/{event_id}/snapshot/before",
        f"/api/v1/camera-events/{event_id}/snapshot/after",
    ]


async def test_without_blurred_frames_the_event_still_goes_but_says_so(tmp_path: Path) -> None:
    """The writer fails closed (no blur, no frame). The alert must still be raised."""
    requests, _ = await _report("shifted", tmp_path, upload=True, fail_snapshots=True)
    assert [r.url.path for r in requests] == ["/api/v1/camera-events"]
    assert _body(requests[0])["has_snapshots"] is False


async def test_a_restored_view_closes_the_open_alert(tmp_path: Path) -> None:
    requests, writer = await _report("restored", tmp_path)
    assert [r.url.path for r in requests] == ["/api/v1/camera-events/restored"]
    assert _body(requests[0])["camera_id"] == "cam30"
    assert writer.written == []


async def test_a_failed_report_never_stops_the_camera(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("api down")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(refuse), base_url="http://api"
    ) as client:
        await _report_view_change(
            client,
            "cam30",
            _change("shifted"),
            _frame(),
            _Pipeline(),  # type: ignore[arg-type]
            _Writer(tmp_path),  # type: ignore[arg-type]
            settings=Settings(snapshots_dir=str(tmp_path)),
            upload_snapshots=False,
        )


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [({}, True), ({"view_monitoring": "off"}, False), ({"view_monitoring": "False"}, False)],
)
def test_view_monitoring_can_be_turned_off_per_camera(
    attributes: dict[str, str], expected: bool
) -> None:
    """A PTZ camera on a patrol tour is meant to change its view."""
    descriptor = CameraDescriptor(camera_id="c", name="c", driver_id="rtsp", attributes=attributes)
    assert _monitors_view(descriptor) is expected


def test_the_camera_condition_puts_a_dark_lens_before_a_moved_view() -> None:
    tamper = TamperDetector()
    view = ViewMonitor()
    assert _camera_condition(None, None) is None
    assert _camera_condition(tamper, None) == "ok"
    view._status = "moved"
    assert _camera_condition(tamper, view) == "moved"
    tamper._current_status = "covered"
    assert _camera_condition(tamper, view) == "covered"
