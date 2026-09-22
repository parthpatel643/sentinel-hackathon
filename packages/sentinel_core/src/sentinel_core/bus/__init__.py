"""Event bus port.

Services depend on this protocol, never on a broker client. NATS JetStream runs
the demo; the production scale plan swaps in Kafka by adding one implementation
and changing configuration — see ADR-004.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from sentinel_core.schemas import Event

__all__ = ["EventBus", "InMemoryEventBus", "subject_matches"]


@runtime_checkable
class EventBus(Protocol):
    """Publish/subscribe over the platform's event envelope."""

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def publish(self, event: Event) -> None: ...

    def subscribe(self, subject_filter: str) -> AsyncIterator[Event]:
        """Yield events matching a subject filter, e.g. `sentinel.events.anpr.*`."""
        ...


class InMemoryEventBus:
    """In-process bus for tests and single-binary development runs."""

    def __init__(self) -> None:
        self._subscribers: list[tuple[str, asyncio.Queue[Event]]] = []
        self.published: list[Event] = []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        self._subscribers.clear()

    async def publish(self, event: Event) -> None:
        self.published.append(event)
        for pattern, queue in self._subscribers:
            if subject_matches(pattern, event.subject):
                await queue.put(event)

    def subscribe(self, subject_filter: str) -> AsyncIterator[Event]:
        # The queue is registered here rather than inside the generator body:
        # an async generator does not execute until first iterated, which would
        # silently drop every event published between subscribe() and the first
        # anext().
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.append((subject_filter, queue))
        return self._drain(queue)

    @staticmethod
    async def _drain(queue: asyncio.Queue[Event]) -> AsyncIterator[Event]:
        while True:
            yield await queue.get()


def subject_matches(pattern: str, subject: str) -> bool:
    """NATS-style subject matching: `*` matches one token, `>` the remainder."""
    p_tokens = pattern.split(".")
    s_tokens = subject.split(".")
    for i, token in enumerate(p_tokens):
        if token == ">":
            return True
        if i >= len(s_tokens):
            return False
        if token not in ("*", s_tokens[i]):
            return False
    return len(p_tokens) == len(s_tokens)
