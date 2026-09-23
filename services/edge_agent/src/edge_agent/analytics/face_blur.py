"""Edge-side default face blurring — docs/05-DELIVERY-PLAN.md's M12 bullet:
"Edge-side default face blurring; reveal-on-authorisation with reason
capture." Every snapshot leaving the edge has faces blurred by default;
the unblurred original is written to a separate, non-served directory
only the reveal workflow (core_api/evidence/reveal.py) can read.

Uses OpenCV's YuNet (`cv2.FaceDetectorYN`), a small modern DNN face
detector from the official OpenCV Zoo — not the classic Haar cascade
(`cv2.CascadeClassifier`) originally reached for here: this repo's pinned
`opencv-python-headless` is OpenCV 5.0, which **removed the legacy
objdetect Haar cascade API entirely** (discovered while building this —
`cv2.CascadeClassifier` no longer exists). YuNet is also just a better
detector: DNN-based, actively maintained, and still cheap enough to run
on every ANPR event without meaningfully competing with the vehicle
detector/plate reader for the edge node's CPU.

The ~230KB ONNX weights are downloaded on first use and cached (same
"model weights are never committed" policy as models/README.md's vehicle
detector/plate reader/OCR models — this one just doesn't yet have a
Python package wrapping its download the way `open-image-models`/
`fast-plate-ocr` do, so this module does it directly with the stdlib).
"""

from __future__ import annotations

import logging
import threading
import urllib.request
from pathlib import Path

import cv2
import numpy as np

__all__ = ["blur_faces", "blur_regions", "detect_faces", "ensure_model_downloaded"]

logger = logging.getLogger(__name__)

_MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
_DEFAULT_MODEL_PATH = (
    Path.home() / ".cache" / "sentinel-platform" / "models" / "face_detection_yunet_2023mar.onnx"
)


def ensure_model_downloaded(model_path: Path = _DEFAULT_MODEL_PATH) -> Path:
    """Idempotent: skips the download if the file already exists, exactly
    like the "Skipping download of '<model>', already exists" behaviour
    the vehicle detector/OCR models already log at worker startup."""
    if model_path.exists():
        return model_path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading face detector model to %s", model_path)
    urllib.request.urlretrieve(_MODEL_URL, model_path)
    return model_path


_detectors = threading.local()


def _detector(model_path_str: str) -> cv2.FaceDetectorYN:
    """One detector **per thread**, deliberately not one per process.

    `FaceDetectorYN` carries mutable state: the input size set by
    `setInputSize` is what the next `detect` call validates its buffer
    against. A single shared instance is therefore not safe to use from more
    than one thread, and this is called from several — each camera pipeline
    runs `process_frame` in its own `asyncio.to_thread` worker, and snapshot
    writing happens inside it.

    Sharing one produced a genuine race: two cameras of different resolutions
    would interleave `setInputSize` and `detect`, so a frame was measured
    against another camera's dimensions and OpenCV aborted with
    `buf.shape() == m.shape()`. Rare, silent and costly — the snapshot for
    that detection was dropped, which on this path means the face blur did
    not happen, so there was no evidence image to fall back to.

    A lock would also fix it, at the cost of serialising every camera's
    snapshot behind one detector. The models are small and already loaded per
    process, so a handful of per-thread copies is the cheaper trade.
    """
    cached: dict[str, cv2.FaceDetectorYN] | None = getattr(_detectors, "by_model", None)
    if cached is None:
        cached = {}
        _detectors.by_model = cached
    detector = cached.get(model_path_str)
    if detector is None:
        model_path = ensure_model_downloaded(Path(model_path_str))
        # cv2's bundled type stubs don't yet know about OpenCV 5.0's
        # FaceDetectorYN_create (a very recent addition) — real at runtime,
        # verified against a live model load and detection, just untyped.
        detector = cv2.FaceDetectorYN_create(str(model_path), "", (320, 320))  # type: ignore[attr-defined]
        cached[model_path_str] = detector
    return detector


def detect_faces(
    image: np.ndarray, *, model_path: Path = _DEFAULT_MODEL_PATH
) -> list[tuple[int, int, int, int]]:
    """Returns (x, y, width, height) boxes for every plausible face in the
    full frame — not just within the vehicle's bounding box, since
    bystanders elsewhere in frame deserve the same default privacy
    protection as the vehicle's own occupants."""
    detector = _detector(str(model_path))
    height, width = image.shape[:2]
    detector.setInputSize((width, height))
    _retval, faces = detector.detect(image)
    if faces is None:
        # cv2's stubs claim this return is non-Optional; empirically false
        # (verified against a live model — an image with no detected faces
        # genuinely returns None here, not an empty array).
        return []  # type: ignore[unreachable]
    boxes = []
    for face in faces:
        x, y, w, h = face[:4]
        boxes.append((max(0, int(x)), max(0, int(y)), int(w), int(h)))
    return boxes


def blur_regions(image: np.ndarray, boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    """The pure, model-free half of face blurring: given (x, y, w, h)
    boxes (wherever they came from), returns a **copy** with those regions
    heavily Gaussian-blurred. Split out from `blur_faces` specifically so
    this logic is unit-testable without the DNN detector — the same
    boundary this codebase already draws around `vehicle_detector.py`'s
    pure `decode_yolo_output` vs. the actual ONNX inference call."""
    blurred = image.copy()
    for x, y, w, h in boxes:
        region = blurred[y : y + h, x : x + w]
        if region.size == 0:
            continue
        # An odd kernel scaled to the face size — small faces still end up
        # genuinely unrecognisable, not just softened.
        kernel = max(15, (min(w, h) // 2) | 1)
        blurred[y : y + h, x : x + w] = cv2.GaussianBlur(region, (kernel, kernel), 0)
    return blurred


def blur_faces(image: np.ndarray, *, model_path: Path = _DEFAULT_MODEL_PATH) -> np.ndarray:
    """Returns a **copy** with every detected face region heavily
    Gaussian-blurred — the input array is never mutated, so a caller that
    also needs the original (to save it separately for the reveal
    workflow) can safely keep using it afterward."""
    return blur_regions(image, detect_faces(image, model_path=model_path))
