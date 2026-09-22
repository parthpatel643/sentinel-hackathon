"""Multi-object tracking — a compact SORT-style tracker (Kalman-filtered IoU
association), vendored as plain MIT code rather than depending on BoxMOT.

BoxMOT (the reference ByteTrack/BoT-SORT/OccluBoost implementation most of
the ANPR literature cites) is AGPL-3.0. ByteTrack's actual matching logic is
Kalman prediction + IoU-cost Hungarian assignment — a few hundred lines with
no ReID network required — so vendoring it here removes the only AGPL
dependency this pipeline would otherwise need beyond the vehicle detector
itself (see 02-ANPR-PIPELINE.md section 8).

This implements single-stage (not ByteTrack's two-confidence-stage) IoU
association — the honest simplification. Two-stage association (matching
low-confidence detections against still-unmatched tracks before giving up on
them) is a documented, bounded upgrade, not a hidden gap.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from edge_agent.analytics.vehicle_detector import VehicleDetection

__all__ = ["SimpleTracker", "TrackedVehicle", "TrackerConfig", "iou_matrix"]


def _as_bbox4(box: np.ndarray) -> tuple[float, float, float, float]:
    """Fixed-arity conversion — VehicleDetection.bbox_xyxy is a 4-tuple, not
    an arbitrary-length one, so this is more than a style preference."""
    x1, y1, x2, y2 = box
    return (float(x1), float(y1), float(x2), float(y2))


def iou_matrix(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """Pairwise IoU between two sets of xyxy boxes. Pure numpy, no OpenCV."""
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)))

    area_a = (boxes_a[:, 2] - boxes_a[:, 0]) * (boxes_a[:, 3] - boxes_a[:, 1])
    area_b = (boxes_b[:, 2] - boxes_b[:, 0]) * (boxes_b[:, 3] - boxes_b[:, 1])

    x1 = np.maximum(boxes_a[:, None, 0], boxes_b[None, :, 0])
    y1 = np.maximum(boxes_a[:, None, 1], boxes_b[None, :, 1])
    x2 = np.minimum(boxes_a[:, None, 2], boxes_b[None, :, 2])
    y2 = np.minimum(boxes_a[:, None, 3], boxes_b[None, :, 3])

    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / union, 0.0)


@dataclass(slots=True)
class TrackedVehicle:
    """A VehicleDetection with a stable identity across frames."""

    track_id: int
    detection: VehicleDetection
    hits: int
    age: int
    """Frames since this track was created."""


@dataclass(slots=True)
class TrackerConfig:
    iou_threshold: float = 0.3
    """Below this, a detection and a track are not considered a match."""
    max_age: int = 30
    """Frames a track survives with no matching detection before it is
    dropped — this is what lets a track survive a brief occlusion or a
    handful of dropped frames without losing the vehicle's identity."""
    min_hits: int = 1
    """Consecutive matches required before a track is reported. 1 means
    report immediately (favours recall); raise for stricter confirmation."""


@dataclass(slots=True)
class _Track:
    track_id: int
    kf: cv2.KalmanFilter
    vehicle_class: str
    confidence: float
    hits: int = 1
    age: int = 0
    time_since_update: int = 0

    def predicted_bbox(self) -> np.ndarray:
        state = self.kf.statePost if self.time_since_update == 0 else self.kf.statePre
        cx, cy, w, h = state[0, 0], state[1, 0], state[2, 0], state[3, 0]
        return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])


def _new_kalman_filter(bbox_xyxy: tuple[float, float, float, float]) -> cv2.KalmanFilter:
    """Constant-velocity model on box centre; width/height tracked directly
    (not differentiated) since plates/vehicles rarely change apparent size
    fast enough between frames for that to matter at CCTV frame rates."""
    kf = cv2.KalmanFilter(6, 4)  # state: [cx, cy, w, h, vcx, vcy]; measurement: [cx, cy, w, h]
    kf.transitionMatrix = np.array(
        [
            [1, 0, 0, 0, 1, 0],
            [0, 1, 0, 0, 0, 1],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1],
        ],
        dtype=np.float32,
    )
    kf.measurementMatrix = np.array(
        [
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, 1, 0, 0],
        ],
        dtype=np.float32,
    )
    kf.processNoiseCov = np.eye(6, dtype=np.float32) * 1e-2
    kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * 1e-1
    kf.errorCovPost = np.eye(6, dtype=np.float32)

    x1, y1, x2, y2 = bbox_xyxy
    cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
    kf.statePost = np.array([[cx], [cy], [w], [h], [0], [0]], dtype=np.float32)
    return kf


class SimpleTracker:
    """Frame-by-frame Kalman-filtered IoU tracker.

    Call `update()` once per frame with that frame's vehicle detections, in
    order. Track ids are stable across calls; a track survives up to
    `max_age` frames with no matching detection, and is discarded after that
    (which resets the temporal-voting window in the ANPR pipeline — see
    docs/01-ARCHITECTURE.md section 5.1).
    """

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.config = config or TrackerConfig()
        self._tracks: list[_Track] = []
        self._next_id = 1

    def update(self, detections: list[VehicleDetection]) -> list[TrackedVehicle]:
        for track in self._tracks:
            track.kf.predict()
            track.age += 1
            track.time_since_update += 1

        matched_track_idx, matched_det_idx = self._associate(detections)

        for track_idx, det_idx in zip(matched_track_idx, matched_det_idx, strict=True):
            self._apply_measurement(self._tracks[track_idx], detections[det_idx])

        unmatched_dets = set(range(len(detections))) - set(matched_det_idx)
        for det_idx in unmatched_dets:
            self._create_track(detections[det_idx])

        self._tracks = [t for t in self._tracks if t.time_since_update <= self.config.max_age]

        return [
            TrackedVehicle(
                track_id=t.track_id,
                detection=VehicleDetection(
                    bbox_xyxy=_as_bbox4(t.predicted_bbox()),
                    vehicle_class=t.vehicle_class,
                    confidence=t.confidence,
                ),
                hits=t.hits,
                age=t.age,
            )
            for t in self._tracks
            if t.hits >= self.config.min_hits and t.time_since_update == 0
        ]

    def _associate(self, detections: list[VehicleDetection]) -> tuple[list[int], list[int]]:
        if not self._tracks or not detections:
            return [], []

        track_boxes = np.array([t.predicted_bbox() for t in self._tracks])
        det_boxes = np.array([d.bbox_xyxy for d in detections])
        ious = iou_matrix(track_boxes, det_boxes)

        row_idx, col_idx = linear_sum_assignment(-ious)  # maximise IoU
        matched_tracks, matched_dets = [], []
        for r, c in zip(row_idx, col_idx, strict=True):
            if ious[r, c] >= self.config.iou_threshold:
                matched_tracks.append(int(r))
                matched_dets.append(int(c))
        return matched_tracks, matched_dets

    def _apply_measurement(self, track: _Track, detection: VehicleDetection) -> None:
        x1, y1, x2, y2 = detection.bbox_xyxy
        cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
        measurement = np.array([[cx], [cy], [w], [h]], dtype=np.float32)
        track.kf.correct(measurement)
        track.hits += 1
        track.time_since_update = 0
        track.confidence = detection.confidence
        track.vehicle_class = detection.vehicle_class

    def _create_track(self, detection: VehicleDetection) -> None:
        track = _Track(
            track_id=self._next_id,
            kf=_new_kalman_filter(detection.bbox_xyxy),
            vehicle_class=detection.vehicle_class,
            confidence=detection.confidence,
        )
        self._next_id += 1
        self._tracks.append(track)

    def reset(self) -> None:
        """Drop all track state. Call on a stream discontinuity (loop cut) —
        a track surviving across a scene cut would silently merge two
        unrelated vehicles under one id."""
        self._tracks.clear()

    @property
    def active_track_ids(self) -> set[int]:
        """Track ids currently alive (matched or within max_age of their last
        match). Used by the pipeline to prune per-track voter state for
        tracks that have aged out — see analytics/pipeline.py."""
        return {t.track_id for t in self._tracks}
