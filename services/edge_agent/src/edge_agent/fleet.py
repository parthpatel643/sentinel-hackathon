"""Keeps the set of running camera pipelines equal to the set the registry
says should be running.

On evaluation day cameras are onboarded while the platform is already live —
a CSV of department feeds, an NVR discovered by its IP, one RTSP URL typed
into the wizard. Each of those must start being analysed without anyone
restarting the worker, and a corrected URL must replace the wrong one rather
than leave the pipeline retrying a typo forever. `CameraFleet.sync` is that
reconciliation: start what is new, restart what changed or died, stop what
was removed.

Stopping is cooperative. A pipeline's capture is an OpenCV handle being read
in a worker thread; cancelling the task mid-read and closing the handle from
another thread is a use-after-free in native code. So a stop sets the
pipeline's stop event, the supervisor finishes the in-flight read and closes
its own capture, and only a pipeline that ignores that for `stop_timeout_s`
is cancelled outright.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from typing import Any

from sentinel_core.schemas import CameraDescriptor, StreamProtocol

__all__ = ["CameraFleet", "FleetChanges"]

logger = logging.getLogger("edge_agent.fleet")

RunCamera = Callable[[CameraDescriptor, asyncio.Event], Coroutine[Any, Any, None]]
OnRemoved = Callable[[CameraDescriptor], Awaitable[None]]


def _stream_identity(descriptor: CameraDescriptor) -> str | None:
    profile = descriptor.profile_for(StreamProtocol.RTSP)
    return profile.url if profile else None


@dataclass(slots=True)
class FleetChanges:
    started: list[str] = field(default_factory=list)
    restarted: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.started or self.restarted or self.stopped)


@dataclass(slots=True)
class _Running:
    descriptor: CameraDescriptor
    task: asyncio.Task[None]
    stop: asyncio.Event


class CameraFleet:
    def __init__(
        self,
        run: RunCamera,
        *,
        on_removed: OnRemoved | None = None,
        stop_timeout_s: float = 40.0,
    ) -> None:
        self._run = run
        self._on_removed = on_removed
        self._stop_timeout_s = stop_timeout_s
        self._running: dict[str, _Running] = {}

    @property
    def camera_ids(self) -> list[str]:
        return sorted(self._running)

    async def sync(self, wanted: Sequence[CameraDescriptor]) -> FleetChanges:
        changes = FleetChanges()
        wanted_by_id = {d.camera_id: d for d in wanted}
        removed: list[_Running] = []
        stopping: list[_Running] = []

        for camera_id, running in list(self._running.items()):
            target = wanted_by_id.get(camera_id)
            if target is None:
                stopping.append(self._running.pop(camera_id))
                removed.append(running)
                changes.stopped.append(camera_id)
            elif _stream_identity(target) != _stream_identity(running.descriptor):
                logger.info("%s: stream URL changed — restarting its pipeline", camera_id)
                stopping.append(self._running.pop(camera_id))
                changes.restarted.append(camera_id)
            elif running.task.done():
                self._log_exit(camera_id, running.task)
                del self._running[camera_id]
                changes.restarted.append(camera_id)

        # Stopped together, not one after another: correcting the URLs of an
        # NVR's sixteen channels must not hold the resync for sixteen stops.
        for running in stopping:
            running.stop.set()
        await asyncio.gather(*(self._await_stop(running) for running in stopping))
        if self._on_removed is not None:
            for running in removed:
                await self._on_removed(running.descriptor)

        for camera_id, descriptor in wanted_by_id.items():
            if camera_id not in self._running:
                self._start(descriptor)
                if camera_id not in changes.restarted:
                    changes.started.append(camera_id)
        return changes

    async def wait(self) -> None:
        """Until every pipeline has ended — how a fixed camera list runs."""
        if self._running:
            await asyncio.gather(*(r.task for r in self._running.values()), return_exceptions=True)

    async def cancel_all(self) -> None:
        """Shutdown: the process is exiting, so there is nothing to protect
        a capture handle for."""
        tasks = [r.task for r in self._running.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._running.clear()

    def _start(self, descriptor: CameraDescriptor) -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(
            self._run(descriptor, stop), name=f"camera:{descriptor.camera_id}"
        )
        self._running[descriptor.camera_id] = _Running(descriptor, task, stop)

    async def _await_stop(self, running: _Running) -> None:
        camera_id = running.descriptor.camera_id
        try:
            await asyncio.wait_for(asyncio.shield(running.task), timeout=self._stop_timeout_s)
        except TimeoutError:
            logger.warning(
                "%s: pipeline did not stop within %.0fs — cancelling it",
                camera_id,
                self._stop_timeout_s,
            )
            running.task.cancel()
            await asyncio.gather(running.task, return_exceptions=True)
        except Exception:
            self._log_exit(camera_id, running.task)

    @staticmethod
    def _log_exit(camera_id: str, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            logger.warning("%s: pipeline was cancelled — restarting it", camera_id)
            return
        exc = task.exception()
        if exc is not None:
            logger.error("%s: pipeline crashed — restarting it", camera_id, exc_info=exc)
        else:
            logger.warning("%s: pipeline ended on its own — restarting it", camera_id)
