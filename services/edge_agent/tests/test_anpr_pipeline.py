"""AnprPipeline end-to-end wiring, using fake vehicle-detector and
plate-reader ports — no model weights, no ONNX Runtime, no network. Mirrors
the fakes.py pattern used for RtspCapture/CameraSupervisor."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from edge_agent.analytics.pipeline import AnprPipeline
from edge_agent.analytics.plate_reader import PlateCandidate
from edge_agent.analytics.vehicle_detector import VehicleDetection
from sentinel_core.clock import Frame, FrameTiming
from sentinel_core.schemas import EventType

ANCHOR = datetime(2026, 9, 22, 9, 0, 0, tzinfo=UTC)


class FakeVehicleDetector:
    """Returns one scripted detection list per call, in order."""

    def __init__(self, scripted: list[list[VehicleDetection]]) -> None:
        self._scripted = scripted
        self._index = 0

    def detect(self, frame: np.ndarray) -> list[VehicleDetection]:
        if self._index >= len(self._scripted):
            return []
        result = self._scripted[self._index]
        self._index += 1
        return result


class FakePlateReader:
    """Returns one scripted candidate list per call, in order — independent
    of what ROI it was actually asked to read, since these tests care about
    pipeline wiring, not real OCR."""

    def __init__(self, scripted: list[list[PlateCandidate]]) -> None:
        self._scripted = scripted
        self._index = 0

    def read(self, image: np.ndarray) -> list[PlateCandidate]:
        if self._index >= len(self._scripted):
            return []
        result = self._scripted[self._index]
        self._index += 1
        return result


def _frame(pts_ms: float, *, discontinuity: bool = False) -> Frame[np.ndarray]:
    timing = FrameTiming(
        camera_id="cam-test",
        pts_ms=pts_ms,
        seq=0,
        stream_epoch=ANCHOR,
        observed_at=ANCHOR,
        delta_ms=40.0,
        is_gap=False,
        is_discontinuity=discontinuity,
    )
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    return Frame(timing=timing, image=image, width=640, height=480)


def _car(x: float = 100.0, y: float = 100.0) -> VehicleDetection:
    return VehicleDetection(
        bbox_xyxy=(x, y, x + 100.0, y + 60.0), vehicle_class="car", confidence=0.9
    )


def _plate(text: str, conf: float = 0.9) -> PlateCandidate:
    return PlateCandidate(
        text=text, char_confidences=tuple(conf for _ in text), bbox_xyxy=(0.0, 0.0, 10.0, 10.0)
    )


def test_first_resolution_emits_exactly_one_event() -> None:
    detector = FakeVehicleDetector([[_car()], [_car()], [_car()]])
    reader = FakePlateReader(
        [[_plate("GJ01AB1234")], [_plate("GJ01AB1234")], [_plate("GJ01AB1234")]]
    )
    pipeline = AnprPipeline(detector, reader, node_id="test-node", model_versions={})

    events = []
    for pts in (40.0, 80.0, 120.0):
        events.extend(pipeline.process_frame(_frame(pts)))

    assert len(events) == 1
    assert events[0].payload.plate_text == "GJ01AB1234"  # type: ignore[union-attr]


def test_no_vehicles_detected_yields_no_events() -> None:
    pipeline = AnprPipeline(
        FakeVehicleDetector([[]]), FakePlateReader([[]]), node_id="n", model_versions={}
    )

    assert pipeline.process_frame(_frame(40.0)) == []


def test_a_changed_resolved_plate_emits_a_second_event() -> None:
    """The vote genuinely improving (more reads agreeing on a better answer)
    must surface as a new event, not be silently swallowed by the
    same-track dedup."""
    detector = FakeVehicleDetector([[_car()]] * 4)
    reader = FakePlateReader(
        [
            [_plate("GJ01AB123X", conf=0.3)],  # low-confidence first read
            [_plate("GJ01AB1234", conf=0.95)],
            [_plate("GJ01AB1234", conf=0.95)],
            [_plate("GJ01AB1234", conf=0.95)],
        ]
    )
    pipeline = AnprPipeline(detector, reader, node_id="n", model_versions={})

    events = []
    for pts in (40.0, 80.0, 120.0, 160.0):
        events.extend(pipeline.process_frame(_frame(pts)))

    plates = [e.payload.plate_text for e in events]  # type: ignore[union-attr]
    assert plates[0] == "GJ01AB123X"
    assert plates[-1] == "GJ01AB1234"


def test_stream_discontinuity_resets_vote_history() -> None:
    """A loop cut must not let a new vehicle inherit the previous vehicle's
    vote history under a coincidentally-reused track id."""
    detector = FakeVehicleDetector([[_car()], [_car()]])
    reader = FakePlateReader([[_plate("GJ01AB1234")], [_plate("MH12CD5678")]])
    pipeline = AnprPipeline(detector, reader, node_id="n", model_versions={})

    first_events = pipeline.process_frame(_frame(40.0))
    second_events = pipeline.process_frame(_frame(0.0, discontinuity=True))

    assert first_events[0].payload.plate_text == "GJ01AB1234"  # type: ignore[union-attr]
    # After the reset, the new vehicle's plate must appear as a fresh first
    # resolution, unaffected by anything seen before the cut.
    assert second_events[0].payload.plate_text == "MH12CD5678"  # type: ignore[union-attr]


def test_event_carries_full_provenance() -> None:
    pipeline = AnprPipeline(
        FakeVehicleDetector([[_car()]]),
        FakePlateReader([[_plate("GJ01AB1234")]]),
        node_id="edge-ahm-01",
        model_versions={"vehicle_det": "yolo11n@1.0", "ocr": "cct-s-v2@1.0"},
    )

    events = pipeline.process_frame(_frame(40.0))

    event = events[0]
    assert event.type == EventType.ANPR_PLATE_READ
    assert event.camera_id == "cam-test"
    assert event.pipeline.node_id == "edge-ahm-01"
    assert event.pipeline.models["ocr"] == "cct-s-v2@1.0"
    assert event.payload.vehicle.vehicle_class == "car"  # type: ignore[union-attr]


def test_bbox_is_attached_to_the_event() -> None:
    pipeline = AnprPipeline(
        FakeVehicleDetector([[_car(x=200.0, y=150.0)]]),
        FakePlateReader([[_plate("GJ01AB1234")]]),
        node_id="n",
        model_versions={},
    )

    events = pipeline.process_frame(_frame(40.0))

    bbox = events[0].payload.bbox  # type: ignore[union-attr]
    assert bbox is not None
    assert bbox.x == 200
    assert bbox.y == 150


def test_two_simultaneous_vehicles_are_voted_independently() -> None:
    detector = FakeVehicleDetector([[_car(x=0.0), _car(x=500.0)]])
    reader = FakePlateReader([[_plate("GJ01AB1234")], [_plate("MH12CD5678")]])
    pipeline = AnprPipeline(detector, reader, node_id="n", model_versions={})

    events = pipeline.process_frame(_frame(40.0))

    plates = {e.payload.plate_text for e in events}  # type: ignore[union-attr]
    assert plates == {"GJ01AB1234", "MH12CD5678"}


def test_stale_voter_state_is_pruned_after_a_track_ages_out() -> None:
    from edge_agent.analytics.tracker import SimpleTracker, TrackerConfig

    tracker = SimpleTracker(TrackerConfig(max_age=1))
    detector = FakeVehicleDetector([[_car()], [], [], []])
    reader = FakePlateReader([[_plate("GJ01AB1234")], [], [], []])
    pipeline = AnprPipeline(detector, reader, node_id="n", model_versions={}, tracker=tracker)

    pipeline.process_frame(_frame(40.0))
    assert len(pipeline._voters) == 1  # accessing internals directly is the point of this test

    pipeline.process_frame(_frame(80.0))
    pipeline.process_frame(_frame(120.0))  # exceeds max_age=1 with no re-match

    assert len(pipeline._voters) == 0


def test_with_no_snapshot_writer_configured_evidence_has_no_snapshot() -> None:
    """The pre-M12 default: nothing breaks for a pipeline that doesn't
    configure a snapshot_writer at all."""
    detector = FakeVehicleDetector([[_car()]])
    reader = FakePlateReader([[_plate("GJ01AB1234")]])
    pipeline = AnprPipeline(detector, reader, node_id="n", model_versions={})

    events = pipeline.process_frame(_frame(40.0))

    assert events[0].evidence.snapshot_uri is None


def test_a_configured_snapshot_writer_is_called_and_its_uri_attached() -> None:
    """M12: proves the pipeline wires a snapshot_writer's return value onto
    the event's evidence ref, whatever that writer actually does — the
    real face-blurring/dual-write logic is snapshot_writer.py's own
    responsibility, tested in test_snapshot_writer.py."""

    class FakeSnapshotWriter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, np.ndarray]] = []

        def write(self, event_id: str, frame_image: np.ndarray) -> str:
            self.calls.append((event_id, frame_image))
            return f"snapshot://{event_id}"

    writer = FakeSnapshotWriter()
    detector = FakeVehicleDetector([[_car()]])
    reader = FakePlateReader([[_plate("GJ01AB1234")]])
    pipeline = AnprPipeline(
        detector, reader, node_id="n", model_versions={}, snapshot_writer=writer
    )

    events = pipeline.process_frame(_frame(40.0))

    assert len(writer.calls) == 1
    called_event_id, _called_frame = writer.calls[0]
    assert called_event_id == events[0].event_id
    assert events[0].evidence.snapshot_uri == f"snapshot://{events[0].event_id}"


def test_a_snapshot_writer_returning_empty_string_leaves_no_snapshot_uri() -> None:
    """SnapshotWriter.write() returns "" on a face-blur failure
    (test_snapshot_writer.py) — the pipeline must not turn that into a
    literal "snapshot://" URI."""

    class FailingSnapshotWriter:
        def write(self, event_id: str, frame_image: np.ndarray) -> str:
            return ""

    detector = FakeVehicleDetector([[_car()]])
    reader = FakePlateReader([[_plate("GJ01AB1234")]])
    pipeline = AnprPipeline(
        detector, reader, node_id="n", model_versions={}, snapshot_writer=FailingSnapshotWriter()
    )

    events = pipeline.process_frame(_frame(40.0))

    assert events[0].evidence.snapshot_uri is None
