"""CameraFleet: the worker-side half of on-site onboarding — a camera added,
corrected or removed in the registry must change what is being analysed
without restarting the worker."""

from __future__ import annotations

import asyncio

import pytest

from edge_agent.fleet import CameraFleet
from sentinel_core.schemas import CameraDescriptor, StreamProfile, StreamProtocol


def _camera(camera_id: str, url: str | None = None) -> CameraDescriptor:
    return CameraDescriptor(
        camera_id=camera_id,
        name=camera_id,
        driver_id="rtsp",
        profiles=[
            StreamProfile(protocol=StreamProtocol.RTSP, url=url or f"rtsp://10.0.0.1/{camera_id}")
        ],
    )


class _Pipelines:
    """Stand-in for `_run_camera`: runs until its stop event is set, the way
    the real supervisor exits its frame loop cooperatively."""

    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.stopped: list[str] = []
        self.crash: set[str] = set()
        self.ignore_stop: set[str] = set()

    async def run(self, descriptor: CameraDescriptor, stop: asyncio.Event) -> None:
        profile = descriptor.profile_for(StreamProtocol.RTSP)
        assert profile is not None
        self.started.append((descriptor.camera_id, profile.url))
        if descriptor.camera_id in self.crash:
            raise RuntimeError("decoder exploded")
        if descriptor.camera_id in self.ignore_stop:
            await asyncio.Event().wait()
        await stop.wait()
        self.stopped.append(descriptor.camera_id)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_new_cameras_are_started() -> None:
    pipelines = _Pipelines()
    fleet = CameraFleet(pipelines.run)

    changes = await fleet.sync([_camera("a"), _camera("b")])
    await _settle()

    assert changes.started == ["a", "b"]
    assert fleet.camera_ids == ["a", "b"]
    assert [cid for cid, _ in pipelines.started] == ["a", "b"]
    await fleet.cancel_all()


async def test_an_unchanged_registry_changes_nothing() -> None:
    pipelines = _Pipelines()
    fleet = CameraFleet(pipelines.run)
    await fleet.sync([_camera("a")])
    await _settle()

    changes = await fleet.sync([_camera("a")])

    assert not changes
    assert len(pipelines.started) == 1
    await fleet.cancel_all()


async def test_a_camera_onboarded_later_joins_without_disturbing_the_rest() -> None:
    pipelines = _Pipelines()
    fleet = CameraFleet(pipelines.run)
    await fleet.sync([_camera("a")])
    await _settle()

    changes = await fleet.sync([_camera("a"), _camera("new")])
    await _settle()

    assert changes.started == ["new"]
    assert pipelines.stopped == []
    await fleet.cancel_all()


async def test_a_corrected_stream_url_restarts_only_that_camera() -> None:
    pipelines = _Pipelines()
    fleet = CameraFleet(pipelines.run)
    await fleet.sync([_camera("a"), _camera("b", "rtsp://10.0.0.1/typo")])
    await _settle()

    changes = await fleet.sync([_camera("a"), _camera("b", "rtsp://10.0.0.1/fixed")])
    await _settle()

    assert changes.restarted == ["b"]
    assert changes.started == []
    assert pipelines.stopped == ["b"]
    assert ("b", "rtsp://10.0.0.1/fixed") in pipelines.started
    await fleet.cancel_all()


async def test_a_removed_camera_is_stopped_cooperatively_and_reported() -> None:
    pipelines = _Pipelines()
    removed: list[str] = []

    async def on_removed(descriptor: CameraDescriptor) -> None:
        removed.append(descriptor.camera_id)

    fleet = CameraFleet(pipelines.run, on_removed=on_removed)
    await fleet.sync([_camera("a"), _camera("b")])
    await _settle()

    changes = await fleet.sync([_camera("a")])

    assert changes.stopped == ["b"]
    # Stopped by its own stop event (so it closed its own capture), not cancelled.
    assert pipelines.stopped == ["b"]
    assert removed == ["b"]
    assert fleet.camera_ids == ["a"]
    await fleet.cancel_all()


async def test_a_crashed_pipeline_is_restarted_on_the_next_sync(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pipelines = _Pipelines()
    pipelines.crash.add("a")
    fleet = CameraFleet(pipelines.run)
    await fleet.sync([_camera("a")])
    await _settle()
    pipelines.crash.clear()

    changes = await fleet.sync([_camera("a")])
    await _settle()

    assert changes.restarted == ["a"]
    assert len(pipelines.started) == 2
    assert "crashed" in caplog.text
    await fleet.cancel_all()


async def test_a_pipeline_that_ignores_stop_is_cancelled_after_the_timeout() -> None:
    pipelines = _Pipelines()
    pipelines.ignore_stop.add("stuck")
    fleet = CameraFleet(pipelines.run, stop_timeout_s=0.05)
    await fleet.sync([_camera("stuck")])
    await _settle()

    changes = await fleet.sync([])

    assert changes.stopped == ["stuck"]
    assert fleet.camera_ids == []


async def test_cancel_all_ends_every_pipeline() -> None:
    pipelines = _Pipelines()
    fleet = CameraFleet(pipelines.run)
    await fleet.sync([_camera("a"), _camera("b")])
    await _settle()

    await fleet.cancel_all()

    assert fleet.camera_ids == []


async def test_many_stops_take_one_timeout_not_one_each() -> None:
    pipelines = _Pipelines()
    pipelines.ignore_stop.update({"a", "b", "c", "d"})
    fleet = CameraFleet(pipelines.run, stop_timeout_s=0.2)
    await fleet.sync([_camera(c) for c in "abcd"])
    await _settle()

    loop = asyncio.get_running_loop()
    started = loop.time()
    changes = await fleet.sync([])

    assert sorted(changes.stopped) == ["a", "b", "c", "d"]
    assert loop.time() - started < 0.6
