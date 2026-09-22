"""The event envelope is the contract between every plane. Breaking it silently
would break evidence provenance, so pin its shape."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sentinel_core.bus import InMemoryEventBus, subject_matches
from sentinel_core.schemas import (
    AnprPayload,
    Event,
    EventType,
    GeoPoint,
    PipelineProvenance,
)

ANCHOR = datetime(2026, 9, 22, 9, 0, 0, tzinfo=UTC)


def _anpr_event(camera_id: str = "GJ-AHM-0421") -> Event:
    return Event(
        type=EventType.ANPR_PLATE_READ,
        camera_id=camera_id,
        device_geo=GeoPoint(lat=23.0225, lon=72.5714),
        pts_ms=1_843_200.0,
        stream_epoch=ANCHOR,
        observed_at=datetime(2026, 9, 22, 9, 30, 43, tzinfo=UTC),
        payload=AnprPayload(
            plate_text="GJ01AB1234",
            plate_normalised="GJ01AB1234",
            plate_ambiguity_key="6J01A81234",
            plate_confidence=0.94,
            char_confidences=[0.99] * 10,
            format_valid=True,
            frames_voted=14,
        ),
        pipeline=PipelineProvenance(
            node_id="edge-local-01",
            models={"plate_det": "yolo-v9-t-640@1.0.0", "ocr": "cct-s-v2@2.0.1"},
        ),
    )


def test_event_ids_are_unique_and_time_sortable() -> None:
    ids = [_anpr_event().event_id for _ in range(50)]

    assert len(set(ids)) == 50
    assert ids == sorted(ids)


def test_event_carries_model_provenance() -> None:
    """Without model versions an alert is an assertion, not evidence."""
    event = _anpr_event()

    assert event.pipeline.models["ocr"] == "cct-s-v2@2.0.1"
    assert event.pipeline.node_id == "edge-local-01"


def test_event_is_immutable_once_emitted() -> None:
    event = _anpr_event()

    with pytest.raises(ValidationError):
        event.camera_id = "tampered"


def test_subject_is_derived_from_type_and_camera() -> None:
    assert _anpr_event().subject == "sentinel.events.anpr.plate_read.GJ-AHM-0421"


def test_confidence_must_be_a_probability() -> None:
    with pytest.raises(ValidationError):
        AnprPayload(
            plate_text="GJ01AB1234",
            plate_normalised="GJ01AB1234",
            plate_ambiguity_key="6J01A81234",
            plate_confidence=1.4,
        )


@pytest.mark.parametrize(
    ("pattern", "subject", "expected"),
    [
        ("sentinel.events.>", "sentinel.events.anpr.plate_read.cam-1", True),
        ("sentinel.events.*.*.cam-1", "sentinel.events.anpr.plate_read.cam-1", True),
        ("sentinel.events.*.*.cam-2", "sentinel.events.anpr.plate_read.cam-1", False),
        ("sentinel.events", "sentinel.events.anpr.plate_read.cam-1", False),
    ],
)
def test_subject_matching(pattern: str, subject: str, expected: bool) -> None:
    assert subject_matches(pattern, subject) is expected


async def test_in_memory_bus_delivers_to_matching_subscribers() -> None:
    bus = InMemoryEventBus()
    stream = bus.subscribe("sentinel.events.anpr.>")
    event = _anpr_event()

    await bus.publish(event)
    # Bounded: a subscriber that misses events should fail the suite, not hang it.
    async with asyncio.timeout(2):
        received = await anext(stream)

    assert received.event_id == event.event_id
    await bus.close()


async def test_subscriber_receives_events_published_before_first_iteration() -> None:
    """An async generator does not run until iterated. If subscribe() deferred
    registration to the generator body, this event would be lost forever."""
    bus = InMemoryEventBus()
    stream = bus.subscribe("sentinel.events.>")

    await bus.publish(_anpr_event("cam-early"))

    async with asyncio.timeout(2):
        received = await anext(stream)
    assert received.camera_id == "cam-early"
    await bus.close()


async def test_non_matching_subscriber_receives_nothing() -> None:
    bus = InMemoryEventBus()
    stream = bus.subscribe("sentinel.events.zone.>")

    await bus.publish(_anpr_event())

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await anext(stream)
    await bus.close()
