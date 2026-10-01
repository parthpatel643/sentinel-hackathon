"""Detections the API could not take are kept and replayed, not lost."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

from edge_agent import worker
from edge_agent.outbox import DetectionOutbox
from sentinel_core.config import Settings


def _body(event_id: str) -> dict[str, Any]:
    return {"event_id": event_id, "camera_id": "cam-1", "plate_text": "GJ01AB1234"}


def test_queued_detections_survive_a_restart_in_order(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite3"
    outbox = DetectionOutbox(path)
    outbox.put("e1", _body("e1"), has_snapshot=True)
    outbox.put("e2", _body("e2"), has_snapshot=False)
    outbox.put("e1", _body("e1"), has_snapshot=True)  # a duplicate is not queued twice
    outbox.close()

    reopened = DetectionOutbox(path)
    queued = reopened.peek()
    reopened.close()

    assert [q.event_id for q in queued] == ["e1", "e2"]
    assert queued[0].payload == _body("e1")
    assert queued[0].has_snapshot and not queued[1].has_snapshot


def test_the_outbox_is_bounded_and_drops_the_oldest(tmp_path: Path) -> None:
    outbox = DetectionOutbox(tmp_path / "o.sqlite3", max_rows=3)
    for i in range(5):
        outbox.put(f"e{i}", _body(f"e{i}"), has_snapshot=False)
    queued = [q.event_id for q in outbox.peek()]
    outbox.close()

    assert queued == ["e2", "e3", "e4"]


@pytest.mark.parametrize(
    ("status", "expected"), [(201, "ok"), (503, "retry"), (429, "retry"), (422, "rejected")]
)
async def test_deliver_classifies_the_api_answer(status: int, expected: str) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=[]))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        outcome = await worker._deliver(
            client, "e1", _body("e1"), has_snapshot=False, settings=Settings()
        )

    assert outcome == expected


async def test_an_unreachable_api_is_a_retry() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(refuse), base_url="http://api"
    ) as client:
        outcome = await worker._deliver(
            client, "e1", _body("e1"), has_snapshot=False, settings=Settings()
        )

    assert outcome == "retry"


async def test_the_drain_replays_once_the_api_is_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outbox = DetectionOutbox(tmp_path / "o.sqlite3")
    for event_id in ("e1", "e2", "e3"):
        outbox.put(event_id, _body(event_id), has_snapshot=False)
    api_up = False
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if not api_up:
            return httpx.Response(503)
        received.append(request.read().decode())
        return httpx.Response(201, json=[])

    monkeypatch.setattr(worker, "OUTBOX_DRAIN_INTERVAL_S", 0.01)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://api"
    ) as client:
        drain = asyncio.create_task(worker._drain_outbox(client, outbox, Settings()))
        await asyncio.sleep(0.05)
        assert len(outbox) == 3  # API down: nothing lost, nothing replayed

        api_up = True
        for _ in range(100):
            await asyncio.sleep(0.01)
            if not len(outbox):
                break
        drain.cancel()
    remaining = len(outbox)
    outbox.close()

    assert remaining == 0
    assert ['"e1"' in r for r in received] == [True, False, False]
    assert len(received) == 3
