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

Time is the stream's PTS, never the number of frames and never arrival time.
Analysed frames are not evenly spaced: the scheduler samples by tier, grid
cameras deliver 3 to 25 fps with gaps, and the gateway replays a buffered GOP
on connect, so the first frames arrive faster than real time. A filter that
steps one unit per frame would turn each of those into a velocity error. The
Kalman transition is rebuilt from the PTS delta on every update, velocity is
in pixels per second, and a lost track ages out after seconds of footage.
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
    """Analysed frames since this track was created: a count, not a time."""


# The analysis rate the noise settings were tuned at (scheduler `sampled_fps`).
# They are expressed per second of stream time, so at this rate the filter
# behaves exactly as the per-frame tuning did, and at any other rate it stays
# right instead of drifting with the frame interval.
_NOMINAL_FPS = 8.0
_POSITION_NOISE_PER_S = 1e-2 * _NOMINAL_FPS  # px^2 per s, on cx, cy, w, h
_VELOCITY_NOISE_PER_S = 1e-2 * _NOMINAL_FPS**3  # (px/s)^2 per s
_INITIAL_VELOCITY_VARIANCE = 1.0 * _NOMINAL_FPS**2  # (px/s)^2: 1 px/frame at 8 fps


@dataclass(slots=True)
class TrackerConfig:
    iou_threshold: float = 0.3
    """Below this, a detection and a track are not considered a match."""
    max_age_s: float = 3.75
    """Seconds of stream time a track survives with no matching detection
    before it is dropped: what lets a track survive a brief occlusion or a
    few dropped frames without losing the vehicle's identity. 3.75 s is the
    30 analysed frames it used to be at the nominal 8 fps."""
    min_hits: int = 1
    """Consecutive matches required before a track is reported. 1 means
    report immediately (favours recall); raise for stricter confirmation."""


@dataclass(slots=True)
class _Track:
    track_id: int
    kf: cv2.KalmanFilter
    vehicle_class: str
    confidence: float
    last_update_pts_ms: float
    hits: int = 1
    age: int = 0
    time_since_update: int = 0
    """Updates since the last match (0: matched on this update)."""

    def predicted_bbox(self) -> np.ndarray:
        state = self.kf.statePost if self.time_since_update == 0 else self.kf.statePre
        cx, cy, w, h = state[0, 0], state[1, 0], state[2, 0], state[3, 0]
        return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])


def _set_interval(kf: cv2.KalmanFilter, dt_s: float) -> None:
    """Point the filter's next prediction `dt_s` seconds of stream time
    ahead: position advances by velocity x dt, and uncertainty grows in
    proportion to the time elapsed, not to the number of frames."""
    transition = np.eye(6, dtype=np.float32)
    transition[0, 4] = transition[1, 5] = dt_s
    kf.transitionMatrix = transition
    kf.processNoiseCov = np.diag([_POSITION_NOISE_PER_S] * 4 + [_VELOCITY_NOISE_PER_S] * 2).astype(
        np.float32
    ) * np.float32(dt_s)


def _new_kalman_filter(bbox_xyxy: tuple[float, float, float, float]) -> cv2.KalmanFilter:
    """Constant-velocity model on box centre, velocity in pixels per second;
    width/height tracked directly (not differentiated) since vehicles rarely
    change apparent size fast enough between frames for that to matter at
    CCTV frame rates."""
    kf = cv2.KalmanFilter(6, 4)  # state: [cx, cy, w, h, vcx, vcy]; measurement: [cx, cy, w, h]
    _set_interval(kf, 0.0)
    kf.measurementMatrix = np.array(
        [
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, 1, 0, 0],
        ],
        dtype=np.float32,
    )
    kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * 1e-1
    kf.errorCovPost = np.diag([1.0] * 4 + [_INITIAL_VELOCITY_VARIANCE] * 2).astype(np.float32)

    x1, y1, x2, y2 = bbox_xyxy
    cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
    kf.statePost = np.array([[cx], [cy], [w], [h], [0], [0]], dtype=np.float32)
    return kf


class SimpleTracker:
    """Kalman-filtered IoU tracker, timed by the stream's PTS.

    Call `update()` once per analysed frame, in stream order, with that
    frame's detections and its PTS. Track ids are stable across calls; a
    track survives `max_age_s` seconds of footage with no matching detection,
    and is discarded after that (which resets the temporal-voting window in
    the ANPR pipeline — see docs/01-ARCHITECTURE.md section 5.1).
    """

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.config = config or TrackerConfig()
        self._tracks: list[_Track] = []
        self._next_id = 1
        self._last_pts_ms: float | None = None

    def update(self, detections: list[VehicleDetection], *, pts_ms: float) -> list[TrackedVehicle]:
        """Advance every track to `pts_ms` and associate this frame's
        detections. `pts_ms` is the frame's presentation timestamp; nothing
        else (frame count, arrival time) may stand in for it."""
        # A frame presented at or before the newest one seen (B-frame
        # reordering within tolerance) advances no time.
        dt_s = 0.0
        if self._last_pts_ms is not None:
            dt_s = max(0.0, pts_ms - self._last_pts_ms) / 1000.0
        self._last_pts_ms = pts_ms if self._last_pts_ms is None else max(self._last_pts_ms, pts_ms)

        for track in self._tracks:
            _set_interval(track.kf, dt_s)
            track.kf.predict()
            track.age += 1
            track.time_since_update += 1

        matched_track_idx, matched_det_idx = self._associate(detections)

        for track_idx, det_idx in zip(matched_track_idx, matched_det_idx, strict=True):
            self._apply_measurement(self._tracks[track_idx], detections[det_idx], pts_ms)

        unmatched_dets = set(range(len(detections))) - set(matched_det_idx)
        for det_idx in unmatched_dets:
            self._create_track(detections[det_idx], pts_ms)

        max_age_ms = self.config.max_age_s * 1000.0
        self._tracks = [t for t in self._tracks if pts_ms - t.last_update_pts_ms <= max_age_ms]

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

    def _apply_measurement(self, track: _Track, detection: VehicleDetection, pts_ms: float) -> None:
        x1, y1, x2, y2 = detection.bbox_xyxy
        cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
        measurement = np.array([[cx], [cy], [w], [h]], dtype=np.float32)
        track.kf.correct(measurement)
        track.hits += 1
        track.time_since_update = 0
        track.last_update_pts_ms = pts_ms
        track.confidence = detection.confidence
        track.vehicle_class = detection.vehicle_class

    def _create_track(self, detection: VehicleDetection, pts_ms: float) -> None:
        track = _Track(
            track_id=self._next_id,
            kf=_new_kalman_filter(detection.bbox_xyxy),
            last_update_pts_ms=pts_ms,
            vehicle_class=detection.vehicle_class,
            confidence=detection.confidence,
        )
        self._next_id += 1
        self._tracks.append(track)

    def reset(self) -> None:
        """Drop all track state. Call on a stream discontinuity (loop cut) —
        a track surviving across a scene cut would silently merge two
        unrelated vehicles under one id. The PTS origin moves with the cut,
        so the previous frame's PTS is forgotten too."""
        self._tracks.clear()
        self._last_pts_ms = None

    @property
    def active_track_ids(self) -> set[int]:
        """Track ids currently alive (matched or within max_age_s of their last
        match). Used by the pipeline to prune per-track voter state for
        tracks that have aged out — see analytics/pipeline.py."""
        return {t.track_id for t in self._tracks}
