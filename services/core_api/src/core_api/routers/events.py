"""Server-sent events stream for the operator console.

`GET /api/v1/events/stream` carries every new or updated watchlist alert and
every zone event as it is recorded, so an alert reaches the screen in well
under a second instead of on the next poll. The console reads it with
`fetch` rather than `EventSource` so the bearer token travels in a header,
never in a URL that proxies and browser history would keep.

Events are filtered by department exactly as Postgres RLS filters the alert
queue: a user scoped to a department sees only its cameras' events.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from core_api.auth.dependencies import current_user
from core_api.auth.service import TokenPayload
from core_api.events.broker import LiveEvent, broker

router = APIRouter(prefix="/api/v1", tags=["events"])

KEEPALIVE_S = 15.0
# uvicorn waits for open responses before it shuts down or reloads, so an
# endless stream would hang `make api`. Each connection ends after this long;
# the console reconnects at once and re-reads the queue, so nothing is lost.
MAX_CONNECTION_S = 30.0


def _visible_to(user: TokenPayload, event: LiveEvent) -> bool:
    return user.department_id is None or event.department_id == user.department_id


def _format(event: LiveEvent) -> str:
    return f"event: {event.kind}\ndata: {json.dumps(event.payload, separators=(',', ':'))}\n\n"


async def _stream(request: Request, user: TokenPayload) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    ends_at = loop.time() + MAX_CONNECTION_S
    async with broker.subscribe() as queue:
        # Tells EventSource-style clients how soon to come back, and flushes
        # the response headers so the client knows the stream is open.
        yield "retry: 1000\n\n"
        while (remaining := ends_at - loop.time()) > 0:
            if await request.is_disconnected():
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=min(KEEPALIVE_S, remaining))
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if _visible_to(user, event):
                yield _format(event)


@router.get("/events/stream")
async def event_stream_endpoint(
    request: Request, user: TokenPayload = Depends(current_user)
) -> StreamingResponse:
    return StreamingResponse(
        _stream(request, user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
