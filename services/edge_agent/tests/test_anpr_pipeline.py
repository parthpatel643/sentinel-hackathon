"""AnprPipeline end-to-end wiring, using fake vehicle-detector and
plate-reader ports — no model weights, no ONNX Runtime, no network. Mirrors
the fakes.py pattern used for RtspCapture/CameraSupervisor."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from edge_agent.analytics.frame_clock import FrameClockReader
from edge_agent.analytics.pipeline import AnprPipeline
from edge_agent.analytics.plate_reader import PlateCandidate
from edge_agent.analytics.vehicle_detector import VehicleDetection
from sentinel_core.clock import Frame, FrameTiming
from sentinel_core.schemas import AnprPayload, EventType

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
    payload = events[0].payload
    assert isinstance(payload, AnprPayload)
    assert payload.plate_text == "GJ01AB1234"


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


def test_vehicle_colour_is_classified_from_the_vehicles_own_bounding_box() -> None:
    """M13: a real red patch at the car's bounding box location must
    genuinely classify as red — this is testing the pipeline's wiring
    (crops the right region, calls the real classifier), not re-testing
    the classifier's own logic (see test_colour.py for that)."""
    timing = FrameTiming(
        camera_id="cam-test",
        pts_ms=40.0,
        seq=0,
        stream_epoch=ANCHOR,
        observed_at=ANCHOR,
        delta_ms=40.0,
        is_gap=False,
        is_discontinuity=False,
    )
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    car = _car(x=100.0, y=100.0)
    x1, y1, x2, y2 = car.bbox_xyxy
    image[int(y1) : int(y2), int(x1) : int(x2)] = (0, 0, 255)  # solid red (BGR), car's own bbox
    frame = Frame(timing=timing, image=image, width=640, height=480)

    detector = FakeVehicleDetector([[car]])
    reader = FakePlateReader([[_plate("GJ01AB1234")]])
    pipeline = AnprPipeline(detector, reader, node_id="n", model_versions={})

    events = pipeline.process_frame(frame)

    assert events[0].payload.vehicle.colour == "red"  # type: ignore[union-attr]


def test_a_small_vehicle_roi_is_widened_with_real_pixels() -> None:
    """The plate detector resizes whatever it is handed to its own input
    size, so a tight crop of a distant motorcycle is upscaled several times
    over before anything reads it — and interpolation cannot invent the
    strokes that separate a J from a 3. Taking more of the surrounding frame
    costs nothing (it is still one inference) and hands the detector pixels
    the sensor actually recorded.
    """
    pipeline = AnprPipeline(
        FakeVehicleDetector([]), FakePlateReader([]), node_id="n", model_versions={}
    )
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)

    roi = pipeline._crop_roi(image, (900.0, 500.0, 1040.0, 730.0))  # 140x230, a far motorbike

    assert roi.shape[0] >= 640 and roi.shape[1] >= 640
    # Still a view of the frame, not an upscaled copy of the crop.
    assert roi.base is image or roi.base is not None


def test_a_large_vehicle_roi_is_left_alone() -> None:
    """A vehicle already bigger than the detector's input needs no help, and
    widening it would only dilute the plate with irrelevant scene."""
    pipeline = AnprPipeline(
        FakeVehicleDetector([]), FakePlateReader([]), node_id="n", model_versions={}
    )
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)

    roi = pipeline._crop_roi(image, (100.0, 100.0, 900.0, 800.0))  # 800x700

    assert roi.shape[1] < 1000  # grew only by the configured margin


def test_a_read_too_short_to_be_a_plate_is_not_reported() -> None:
    """Fragments like "1" or "111" are not weak evidence, they are no
    evidence. Indian plate grammar admits nothing shorter than eight
    characters and the matching ladder reaches two edits, so a read below six
    could not resolve to a real registration however it were matched.

    They were 28% of stored detections on a live camera, and the cost is not
    just noise: two cameras both reading "1" is indistinguishable from one
    vehicle seen in two places, which would put a fabricated journey in front
    of an operator.
    """
    detection = VehicleDetection(
        bbox_xyxy=(10.0, 10.0, 90.0, 90.0), vehicle_class="car", confidence=0.9
    )
    pipeline = AnprPipeline(
        FakeVehicleDetector([[detection]]),
        FakePlateReader(
            [[PlateCandidate(text="1", char_confidences=(0.9,), bbox_xyxy=(0, 0, 5, 5))]]
        ),
        node_id="n",
        model_versions={},
    )

    assert pipeline.process_frame(_frame(0.0)) == []


def test_a_full_length_plate_is_still_reported() -> None:
    """The guard must not swallow real reads — the same path with a genuine
    registration still emits."""
    detection = VehicleDetection(
        bbox_xyxy=(10.0, 10.0, 90.0, 90.0), vehicle_class="car", confidence=0.9
    )
    plate = PlateCandidate(
        text="GJ01AB1234",
        char_confidences=tuple(0.9 for _ in "GJ01AB1234"),
        bbox_xyxy=(0, 0, 5, 5),
    )
    pipeline = AnprPipeline(
        FakeVehicleDetector([[detection]]),
        FakePlateReader([[plate]]),
        node_id="n",
        model_versions={},
    )

    events = pipeline.process_frame(_frame(0.0))

    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, AnprPayload)
    assert payload.plate_text == "GJ01AB1234"


def test_a_settled_plate_is_not_reread_on_every_frame() -> None:
    from edge_agent.analytics.voting import SETTLED_AFTER_READS, SETTLED_RECHECK_EVERY

    frames = SETTLED_AFTER_READS + SETTLED_RECHECK_EVERY
    detector = FakeVehicleDetector([[_car()] for _ in range(frames)])
    reader = FakePlateReader([[_plate("GJ01AB1234")] for _ in range(frames)])
    pipeline = AnprPipeline(detector, reader, node_id="n", model_versions={})

    for i in range(frames):
        pipeline.process_frame(_frame(i * 40.0))

    # Every frame until the vote settles, then one recheck in the next eight.
    assert reader._index == SETTLED_AFTER_READS + 1


def test_people_are_tracked_apart_from_vehicles_and_never_read() -> None:
    person = VehicleDetection(
        bbox_xyxy=(300.0, 100.0, 340.0, 220.0), vehicle_class="person", confidence=0.9
    )
    detector = FakeVehicleDetector([[_car(), person]])
    reader = FakePlateReader([[_plate("GJ01AB1234")]])
    pipeline = AnprPipeline(detector, reader, node_id="n", model_versions={})

    pipeline.process_frame(_frame(0.0))

    assert len(pipeline.last_tracked_vehicles) == 1
    assert [p.detection.vehicle_class for p in pipeline.last_tracked_people] == ["person"]
    assert reader._index == 1  # the plate reader saw the car only


# --- The camera's clock: the only time a sighting is reported with ----------


def _clock_reader(overlays: dict[int, str]) -> FrameClockReader:
    """A clock reader whose OCR sees `overlays[marker]` on a frame whose
    top-left pixel is `marker` — each test frame shows its own clock."""
    clock = FrameClockReader()
    clock._ocr = lambda image: overlays.get(int(image[0, 0, 0]))  # type: ignore[method-assign, assignment]
    return clock


def _marked_frame(pts_ms: float, marker: int, **kwargs: bool) -> Frame[np.ndarray]:
    frame = _frame(pts_ms, **kwargs)
    frame.image[0, 0, 0] = marker
    return frame


class _RecordingSnapshotWriter:
    def __init__(self) -> None:
        self.images: list[np.ndarray] = []

    def write(self, event_id: str, frame_image: np.ndarray) -> str:
        self.images.append(frame_image)
        return f"snapshot://{event_id}"


def test_a_sighting_takes_its_time_and_snapshot_from_a_frame_whose_clock_was_read() -> None:
    """The plate resolves on a frame whose overlay is unreadable. The newest
    earlier frame of the same vehicle with a confirmed clock becomes the
    evidence: its image, its box, and the time printed on it — so the time
    reported is the time visible in the snapshot."""
    clock = _clock_reader({1: "17-06-2026 18:04:42", 2: "17-06-2026 18:04:43"})
    writer = _RecordingSnapshotWriter()
    detector = FakeVehicleDetector([[_car(100.0)], [_car(110.0)], [_car(120.0)]])
    reader = FakePlateReader([[], [], [_plate("GJ01AB1234")]])
    pipeline = AnprPipeline(
        detector, reader, node_id="n", model_versions={}, snapshot_writer=writer, frame_clock=clock
    )

    frames = [_marked_frame(1000.0, 1), _marked_frame(2000.0, 2), _marked_frame(3000.0, 3)]
    events = pipeline.process_frame(frames[0])
    events += pipeline.process_frame(frames[1])
    box_on_second_frame = pipeline.last_tracked_vehicles[0].detection.bbox_xyxy
    events += pipeline.process_frame(frames[2])

    assert len(events) == 1
    event = events[0]
    assert event.camera_time == datetime(2026, 6, 17, 12, 34, 43, tzinfo=UTC)
    assert writer.images[0] is frames[1].image
    payload = event.payload
    assert isinstance(payload, AnprPayload)
    assert payload.bbox is not None
    assert payload.bbox.x == int(box_on_second_frame[0])


def test_with_no_readable_clock_the_time_is_unknown() -> None:
    """Nothing stands in for the camera's clock: not the stream's PTS, not
    when we processed the frame. The processing time stays on observed_at
    for internal ordering only."""
    pipeline = AnprPipeline(
        FakeVehicleDetector([[_car()]]),
        FakePlateReader([[_plate("GJ01AB1234")]]),
        node_id="n",
        model_versions={},
        frame_clock=_clock_reader({}),
    )
    events = pipeline.process_frame(_marked_frame(1000.0, 1))
    assert len(events) == 1
    assert events[0].camera_time is None
    assert events[0].observed_at == ANCHOR


def test_an_unconfirmed_reading_is_not_a_time() -> None:
    """One reading with nothing to agree with could be a misread digit."""
    pipeline = AnprPipeline(
        FakeVehicleDetector([[_car()]]),
        FakePlateReader([[_plate("GJ01AB1234")]]),
        node_id="n",
        model_versions={},
        frame_clock=_clock_reader({1: "17-06-2026 18:04:42"}),
    )
    events = pipeline.process_frame(_marked_frame(1000.0, 1))
    assert events[0].camera_time is None


def test_the_sightings_own_frame_is_read_when_no_earlier_frame_was() -> None:
    """The once-a-second read happened on a frame without this vehicle; the
    plate resolves later in the same second. Its own frame's clock is read
    and confirmed by the earlier reading."""
    clock = _clock_reader({1: "17-06-2026 18:04:42", 2: "17-06-2026 18:04:42"})
    pipeline = AnprPipeline(
        FakeVehicleDetector([[], [_car()]]),
        FakePlateReader([[_plate("GJ01AB1234")]]),
        node_id="n",
        model_versions={},
        frame_clock=clock,
    )
    pipeline.process_frame(_marked_frame(1000.0, 1))
    events = pipeline.process_frame(_marked_frame(1500.0, 2))
    assert events[0].camera_time == datetime(2026, 6, 17, 12, 34, 42, tzinfo=UTC)


def test_a_stream_discontinuity_forgets_earlier_clock_readings() -> None:
    """After a scene cut the PTS origin moves, so a reading before it cannot
    confirm one after it."""
    clock = _clock_reader({1: "17-06-2026 18:04:42", 2: "17-06-2026 18:04:43"})
    pipeline = AnprPipeline(
        FakeVehicleDetector([[], [_car()]]),
        FakePlateReader([[_plate("GJ01AB1234")]]),
        node_id="n",
        model_versions={},
        frame_clock=clock,
    )
    pipeline.process_frame(_marked_frame(1000.0, 1))
    events = pipeline.process_frame(_marked_frame(2000.0, 2, discontinuity=True))
    assert events[0].camera_time is None


def test_camera_time_of_reads_a_frame_for_events_with_no_vehicle_evidence() -> None:
    """Zone events have no snapshot; their time is the clock on the frame
    that fired them, confirmed the same way."""
    clock = _clock_reader({1: "17-06-2026 18:04:42", 2: "17-06-2026 18:04:43"})
    pipeline = AnprPipeline(
        FakeVehicleDetector([]),
        FakePlateReader([]),
        node_id="n",
        model_versions={},
        frame_clock=clock,
    )
    pipeline.process_frame(_marked_frame(1000.0, 1))
    assert pipeline.camera_time_of(_marked_frame(2000.0, 2)) == datetime(
        2026, 6, 17, 12, 34, 43, tzinfo=UTC
    )
    assert (
        AnprPipeline(
            FakeVehicleDetector([]), FakePlateReader([]), node_id="n", model_versions={}
        ).camera_time_of(_marked_frame(2000.0, 2))
        is None
    )
