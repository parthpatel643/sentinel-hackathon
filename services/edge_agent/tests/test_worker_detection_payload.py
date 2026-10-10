"""The detection payload the worker sends to the core API."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from edge_agent.worker import _event_to_detection_payload
from sentinel_core.schemas import AnprPayload, Event, EventType, PipelineProvenance

PROCESSED_AT = datetime(2026, 10, 8, 8, 47, 19, tzinfo=UTC)


def _event(camera_time: datetime | None) -> Event:
    return Event(
        type=EventType.ANPR_PLATE_READ,
        camera_id="cam06",
        pts_ms=1000.0,
        stream_epoch=PROCESSED_AT,
        observed_at=PROCESSED_AT,
        camera_time=camera_time,
        payload=AnprPayload(
            plate_text="GJ11CD8389",
            plate_normalised="GJ11CD8389",
            plate_ambiguity_key="GJLLCD8389",
            plate_confidence=0.9,
        ),
        pipeline=PipelineProvenance(node_id="n", models={}),
    )


@pytest.mark.parametrize(
    ("camera_time", "sent"),
    [
        (datetime(2026, 6, 17, 12, 35, 28, tzinfo=UTC), "2026-06-17T12:35:28+00:00"),
        (None, None),
    ],
)
def test_the_payload_carries_the_cameras_clock_or_nothing(
    camera_time: datetime | None, sent: str | None
) -> None:
    """The camera's clock goes to the API as-is; an unreadable clock is sent
    as None, never filled in with the processing time."""
    payload = _event_to_detection_payload(_event(camera_time))
    assert payload["camera_time"] == sent
    assert payload["observed_at"] == PROCESSED_AT.isoformat()
