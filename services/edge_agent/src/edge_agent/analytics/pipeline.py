"""End-to-end ANPR pipeline: detect -> track -> read plate -> vote -> event.

Depends on `VehicleDetectorPort` / `PlateReaderPort` protocols rather than the
concrete ONNX/fast-alpr classes directly, so this module is unit tested with
fakes (no model weights, no ONNX Runtime, no network) — the same pattern used
for RtspCapture's fake VideoSource and CameraSupervisor's fake capture
factory throughout this codebase.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol

import numpy as np

from edge_agent.analytics.colour import classify_vehicle_colour
from edge_agent.analytics.frame_clock import FrameClockReader
from edge_agent.analytics.plate_reader import PlateCandidate
from edge_agent.analytics.tracker import SimpleTracker, TrackedVehicle
from edge_agent.analytics.vehicle_detector import VehicleDetection
from edge_agent.analytics.voting import PlateVoter, VotedPlate
from sentinel_core.clock import Frame
from sentinel_core.schemas import (
    AnprPayload,
    BoundingBox,
    Event,
    EventType,
    EvidenceRef,
    PipelineProvenance,
    VehicleAttributes,
)

logger = logging.getLogger(__name__)

__all__ = ["AnprPipeline", "PlateReaderPort", "SnapshotWriterPort", "VehicleDetectorPort"]


class VehicleDetectorPort(Protocol):
    def detect(self, frame: np.ndarray) -> list[VehicleDetection]: ...


class PlateReaderPort(Protocol):
    def read(self, image: np.ndarray) -> list[PlateCandidate]: ...


class SnapshotWriterPort(Protocol):
    """M12: `edge_agent.analytics.snapshot_writer.SnapshotWriter` — writes a
    face-blurred snapshot plus its unblurred original and returns the
    `snapshot_uri` to attach to the event's evidence ref. Optional: a
    pipeline with none configured simply emits events with no snapshot,
    same as every event did before M12."""

    def write(self, event_id: str, frame_image: np.ndarray) -> str: ...


class AnprPipeline:
    """One instance per camera. Feed it frames in PTS order; it emits an
    ANPR event each time a track's resolved plate changes — not every frame,
    which would flood the event bus with near-duplicate reads of a vehicle
    sitting at a red light (see docs/01-ARCHITECTURE.md section 6.2, which
    handles the complementary dedup on the alerting side)."""

    def __init__(
        self,
        vehicle_detector: VehicleDetectorPort,
        plate_reader: PlateReaderPort,
        *,
        node_id: str,
        model_versions: dict[str, str],
        tracker: SimpleTracker | None = None,
        roi_margin: float = 0.1,
        snapshot_writer: SnapshotWriterPort | None = None,
        frame_clock: FrameClockReader | None = None,
    ) -> None:
        self._vehicle_detector = vehicle_detector
        self._plate_reader = plate_reader
        self._tracker = tracker or SimpleTracker()
        self._node_id = node_id
        self._model_versions = model_versions
        self._roi_margin = roi_margin
        self._snapshot_writer = snapshot_writer
        # Reads the camera's own burned-in clock. When it can, that becomes the
        # event's observed_at — see _build_event.
        self._frame_clock = frame_clock
        self._camera_time: datetime | None = None
        self._voters: dict[int, PlateVoter] = {}
        self._last_emitted: dict[int, str] = {}
        # M13: the most recent frame's tracked vehicles, exposed for a
        # caller (edge_agent.worker) to feed into a ZoneRuleEngine —
        # zone rules need every tracked vehicle's position, not just the
        # ones that happen to have a resolved plate this frame.
        self.last_tracked_vehicles: list[TrackedVehicle] = []

    def process_frame(self, frame: Frame[np.ndarray]) -> list[Event]:
        # Once per frame, not once per event: several vehicles can be read
        # from one frame and they all share the camera's clock.
        if self._frame_clock is not None:
            self._camera_time = self._frame_clock.read(frame.image, pts_ms=frame.timing.pts_ms)

        if frame.timing.is_discontinuity:
            # The scene just cut (a loop point in the test grid, or a real
            # camera reboot). A track surviving across it would silently
            # merge two unrelated vehicles under one id and one vote history.
            self._tracker.reset()
            self._voters.clear()
            self._last_emitted.clear()

        vehicle_detections = self._vehicle_detector.detect(frame.image)
        tracked_vehicles = self._tracker.update(vehicle_detections)
        self.last_tracked_vehicles = tracked_vehicles

        events = [
            event
            for tracked in tracked_vehicles
            if (event := self._process_track(frame, tracked)) is not None
        ]

        self._prune_stale_voters()
        return events

    def _process_track(self, frame: Frame[np.ndarray], tracked: TrackedVehicle) -> Event | None:
        roi = self._crop_roi(frame.image, tracked.detection.bbox_xyxy)
        if roi.size == 0:
            return None

        candidates = self._plate_reader.read(roi)
        voter = self._voters.setdefault(tracked.track_id, PlateVoter())
        for candidate in candidates:
            voter.add(candidate)

        voted = voter.resolve()
        if voted is None:
            return None
        if self._last_emitted.get(tracked.track_id) == voted.plate_text:
            return None  # unchanged since the last emission for this track

        self._last_emitted[tracked.track_id] = voted.plate_text
        return self._build_event(frame, tracked, voted)

    def _crop_roi(
        self, image: np.ndarray, bbox_xyxy: tuple[float, float, float, float]
    ) -> np.ndarray:
        height, width = image.shape[:2]
        x1, y1, x2, y2 = bbox_xyxy
        margin_x, margin_y = (x2 - x1) * self._roi_margin, (y2 - y1) * self._roi_margin
        x1 = max(0, int(x1 - margin_x))
        y1 = max(0, int(y1 - margin_y))
        x2 = min(width, int(x2 + margin_x))
        y2 = min(height, int(y2 + margin_y))
        if x2 <= x1 or y2 <= y1:
            return image[0:0, 0:0]
        return image[y1:y2, x1:x2]

    def _build_event(
        self, frame: Frame[np.ndarray], tracked: TrackedVehicle, voted: VotedPlate
    ) -> Event:
        x1, y1, x2, y2 = tracked.detection.bbox_xyxy
        event = Event(
            type=EventType.ANPR_PLATE_READ,
            camera_id=frame.camera_id,
            pts_ms=frame.timing.pts_ms,
            stream_epoch=frame.timing.stream_epoch,
            # The camera's own burned-in time when it is readable, because
            # that is when the scene happened; the PTS-derived time says when
            # we processed it, which for looped recordings can be months
            # later. Nothing is lost by preferring it — pts_ms and
            # stream_epoch above still reconstruct the processing clock
            # exactly.
            observed_at=self._camera_time or frame.observed_at,
            payload=AnprPayload(
                plate_text=voted.plate_text,
                plate_normalised=voted.plate_normalised,
                plate_ambiguity_key=voted.plate_ambiguity_key,
                plate_confidence=voted.plate_confidence,
                char_confidences=list(voted.char_confidences),
                format_valid=voted.format_valid,
                frames_voted=voted.frames_voted,
                bbox=BoundingBox(x=int(x1), y=int(y1), width=int(x2 - x1), height=int(y2 - y1)),
                vehicle=VehicleAttributes(
                    vehicle_class=tracked.detection.vehicle_class,
                    colour=self._classify_colour(frame.image, tracked.detection.bbox_xyxy),
                    track_id=str(tracked.track_id),
                ),
            ),
            pipeline=PipelineProvenance(node_id=self._node_id, models=self._model_versions),
        )
        if self._snapshot_writer is not None:
            # M12: a face-blurred-by-default snapshot of the *full frame*
            # (not just the plate ROI) — bystanders elsewhere in shot get
            # the same default privacy protection as the vehicle's own
            # occupants. See snapshot_writer.py/face_blur.py.
            snapshot_uri = self._snapshot_writer.write(event.event_id, frame.image)
            if snapshot_uri:
                event = event.model_copy(
                    update={"evidence": EvidenceRef(snapshot_uri=snapshot_uri)}
                )
        return event

    def _classify_colour(
        self, image: np.ndarray, bbox_xyxy: tuple[float, float, float, float]
    ) -> str | None:
        """M13: the vehicle's own bounding box (not the margin-expanded
        plate ROI `_crop_roi` produces) — colour is a body-paint signal,
        not a plate-region one."""
        height, width = image.shape[:2]
        x1, y1, x2, y2 = bbox_xyxy
        crop = image[max(0, int(y1)) : min(height, int(y2)), max(0, int(x1)) : min(width, int(x2))]
        try:
            return classify_vehicle_colour(crop)
        except Exception:
            # A colour-classification failure is cosmetic (one optional
            # attribute), never worth losing the plate-read event over.
            logger.exception("vehicle colour classification failed")
            return None

    def _prune_stale_voters(self) -> None:
        """Drop vote history for tracks the tracker has aged out — otherwise
        a track_id that is later reused (after the counter wraps, in a very
        long-running process) would inherit a stale vote history."""
        active = self._tracker.active_track_ids
        for stale_id in set(self._voters) - active:
            del self._voters[stale_id]
        for stale_id in set(self._last_emitted) - active:
            del self._last_emitted[stale_id]
