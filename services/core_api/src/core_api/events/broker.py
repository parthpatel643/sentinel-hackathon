"""Live operator events: new and updated watchlist alerts, and zone events,
pushed to every open console the moment they are recorded.

In-process publish/subscribe, deliberately: the API runs as one process per
command centre in this deployment (docs/01-ARCHITECTURE.md), so a broker in
memory delivers with no extra moving part. A multi-replica deployment swaps
this for the NATS subject the event envelope already defines, without
touching publishers or the stream endpoint.

Each subscriber has a bounded queue. A console that stops reading loses its
oldest events rather than growing memory without bound — the alert queue
itself is the system of record, and the console re-reads it on reconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core_api.db.models import Camera

__all__ = ["EventBroker", "LiveEvent", "broker", "publish_models"]

_QUEUE_SIZE = 256


@dataclass(frozen=True, slots=True)
class LiveEvent:
    kind: str
    """'alert' | 'zone_event' | 'camera_event'"""
    payload: dict[str, Any]
    department_id: str | None
    """Owning department of the camera, for the same scoping RLS applies to
    the alert queue. None for a camera with no department."""


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[LiveEvent]] = set()

    def publish(self, event: LiveEvent) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[LiveEvent]]:
        queue: asyncio.Queue[LiveEvent] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


broker = EventBroker()


async def publish_models(
    session: AsyncSession, kind: str, items: Sequence[tuple[str, BaseModel]]
) -> None:
    """Publish (camera_id, response model) pairs, each tagged with its
    camera's department. Call after the transaction commits, so a console is
    never told about a row a rollback then removed."""
    if not items or broker.subscriber_count == 0:
        return
    camera_ids = {camera_id for camera_id, _ in items}
    rows = await session.execute(
        select(Camera.camera_id, Camera.department_id).where(Camera.camera_id.in_(camera_ids))
    )
    departments: dict[str, object] = {row[0]: row[1] for row in rows.all()}
    for camera_id, model in items:
        department = departments.get(camera_id)
        broker.publish(
            LiveEvent(
                kind=kind,
                payload=model.model_dump(mode="json"),
                department_id=str(department) if department else None,
            )
        )
