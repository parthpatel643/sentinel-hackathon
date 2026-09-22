"""A programmable VideoSource test double.

Lets capture and supervisor tests exercise exact scenarios — a dead camera, a
stream that goes bad after N frames, a loop cut at a specific PTS — without a
live RTSP dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

FPS_PROP = 5  # cv2.CAP_PROP_FPS
POS_MSEC_PROP = 0  # cv2.CAP_PROP_POS_MSEC
HW_ACCEL_PROP = 50  # cv2.CAP_PROP_HW_ACCELERATION


@dataclass
class FakeFrame:
    pts_ms: float
    ok: bool = True


@dataclass
class FakeVideoSource:
    """Replays a scripted sequence of frames (or failures) with a declared fps.

    `should_fail_open` simulates a camera that is simply unreachable.
    """

    frames: list[FakeFrame] = field(default_factory=list)
    declared_fps: float = 25.0
    should_fail_open: bool = False
    width: int = 64
    height: int = 48

    _opened: bool = field(default=False, init=False)
    _index: int = field(default=0, init=False)
    released: bool = field(default=False, init=False)

    def isOpened(self) -> bool:  # noqa: N802 - matches cv2's naming
        return self._opened

    def open_if_permitted(self) -> None:
        self._opened = not self.should_fail_open

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._index >= len(self.frames):
            return False, None
        frame = self.frames[self._index]
        self._index += 1
        if not frame.ok:
            return False, None
        image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        return True, image

    def get(self, prop_id: int) -> float:
        if prop_id == FPS_PROP:
            return self.declared_fps
        if prop_id == POS_MSEC_PROP:
            if self._index == 0:
                return 0.0
            return self.frames[self._index - 1].pts_ms
        return 0.0

    def set(self, prop_id: int, value: float) -> bool:
        return True

    def release(self) -> None:
        self.released = True

    def rewind(self) -> None:
        """Test-only helper: replay this source's script from the start, as a
        fresh connection would after a reconnect."""
        self._index = 0


def make_backend_factory(source: FakeVideoSource) -> Callable[[str], FakeVideoSource]:
    """Wraps a pre-built FakeVideoSource as a `backend_factory(url)` callable,
    opening it (or not) exactly once, the way a real cv2.VideoCapture would."""

    def factory(_url: str) -> FakeVideoSource:
        source.open_if_permitted()
        return source

    return factory
