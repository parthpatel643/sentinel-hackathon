"""Reading the camera's own clock off the frame.

Cameras burn a timestamp into every frame:

    17-06-2026 18:04:42

That is the *camera's* record of when the footage was captured, and it is the
only time this system attaches to a sighting. Nothing else stands in for it:
not the stream's PTS, not when we processed the frame. The grid replays
recordings, so a frame processed today can show June — and it is June that
belongs in evidence.

A reading is used only when another reading of the same camera's clock agrees
with it, after allowing for the footage between them. One inserted digit
turns 21:02 into 21:10 and parses perfectly; agreement is how a misread is
told apart from the clock. The elapsed footage is used for that comparison
only — it is never added to a reading to produce a time, because a camera's
footage can jump (a stitched recording, a scene cut) and its clock jumps with
it.

The overlay is read with PP-OCRv6 (small detection and recognition models,
ONNX, bundled with the `rapidocr` package so nothing is fetched at runtime).
On a hand-labelled holdout from the government grid it reads the exact
timestamp on 98.9% of frames with a legible clock, against 69.0% for the
Tesseract reader it replaced (evidence/CLOCK-READER-ACCURACY.md). The first
read of a camera finds the clock with the detector; after that only the
remembered box is recognised, about 15 ms on a CPU.

Deliberately degrades rather than guesses. If the OCR models cannot load, if
no edge of the frame holds a readable clock, or if nothing agrees with a
reading, the answer is None and the sighting is recorded as "time unknown".
An evidence trail with a confidently wrong time is worse than one that admits
it does not know. The models read damaged digits with full confidence, so
agreement between readings, not a confidence score, is what keeps a misread
out of evidence.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Protocol

import numpy as np

__all__ = ["IST", "FrameClockReader", "PaddleTextEngine", "parse_overlay_timestamp"]

logger = logging.getLogger(__name__)

# Gujarat. The overlay is the camera's local wall clock with no zone marker,
# so the offset has to come from somewhere — configured rather than guessed,
# and applied explicitly so the stored UTC value is auditable.
IST = timezone(timedelta(hours=5, minutes=30))

# Tolerant on purpose. OCR reliably reads the digits of these OSD fonts but
# drops separators unpredictably — real observed output includes
# "17-06-202618:04:42" and "13-06-2026 2102:28". The digits are what matter.
_TIME = r"\D*?(?P<hour>\d{2})\D?(?P<minute>\d{2})\D?(?P<second>\d{2})(?:\s*(?P<meridiem>[AP]M))?"
# `2026-08-03 Mon 21:00:43`: year first. Tried before day-first because a
# day-first pattern can match inside it ("26-08-03..." is not a date, but
# the digits after it can be mistaken for one).
_YEAR_FIRST_RE = re.compile(r"(?P<year>20\d{2})\D?(?P<month>\d{2})\D?(?P<day>\d{2})" + _TIME)
# `17-06-2026 18:04:42`, `13/06/2026 21:01:32 Sat`, `14-06-2026 12:00:30 AM`.
_DAY_FIRST_RE = re.compile(r"(?P<day>\d{2})\D?(?P<month>\d{2})\D?(?P<year>\d{4})" + _TIME)


def parse_overlay_timestamp(text: str, *, tz: timezone = IST) -> datetime | None:
    """Parse an overlay timestamp, tolerating dropped separators.

    Accepts day-first (`DD-MM-YYYY`, `DD/MM/YYYY`) and year-first
    (`YYYY-MM-DD`) dates, a weekday anywhere, and a 12-hour clock with AM/PM.
    Returns an aware UTC datetime, or None when the text holds no timestamp
    that can be real — which is how a misread digit usually shows up.
    """
    for pattern in (_YEAR_FIRST_RE, _DAY_FIRST_RE):
        for match in pattern.finditer(text):
            parsed = _to_datetime(match, tz)
            if parsed is not None:
                return parsed
    return None


def _to_datetime(match: re.Match[str], tz: timezone) -> datetime | None:
    hour = int(match["hour"])
    meridiem = match["meridiem"]
    if meridiem is not None:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "PM" else 0)
    try:
        local = datetime(
            year=int(match["year"]),
            month=int(match["month"]),
            day=int(match["day"]),
            hour=hour,
            minute=int(match["minute"]),
            second=int(match["second"]),
            tzinfo=tz,
        )
    except ValueError:
        # e.g. a misread turning 06 into 16 for the month.
        return None
    if not (2000 <= local.year <= 2100):
        return None
    return local.astimezone(UTC)


# Edges of the frame where the fleet prints its clock, as fractions of the
# height so they hold across 720p, 1080p and 1440p. Each band spans the full
# width: the fleet uses top-left, top-right and bottom-left.
_BANDS: tuple[tuple[float, float], ...] = ((0.0, 0.13), (0.87, 1.0))
# A remembered clock box is recognised with this much margin around it, as a
# fraction of the box height: overlays shift a few pixels between frames.
_BOX_MARGIN = 0.15

_DIGITS = re.compile(r"\d")
_TIME_LIKE = re.compile(r"\d{2}\D?\d{2}\D?\d{2}")
_COMPANION = re.compile(r"^(?:[AP]M|Mon|Tue|Wed|Thu|Fri|Sat|Sun)$", re.IGNORECASE)

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 in pixels of the image read


class TextEngine(Protocol):
    """The OCR models behind the reader: `find` detects and reads every text
    line in an image; `read` recognises one line that is already cropped."""

    def find(self, image: np.ndarray) -> list[tuple[str, Box]]: ...

    def read(self, image: np.ndarray) -> str | None: ...


class PaddleTextEngine:
    """PP-OCRv6 small detection + recognition through RapidOCR on ONNX
    Runtime, CPU only. Loaded once per process and shared by every camera's
    reader: one set of sessions instead of one per camera, and calls are
    serialised so concurrent cameras do not oversubscribe the cores the
    vehicle and plate models also need."""

    def __init__(self, *, det_side: int = 960, threads: int = 2) -> None:
        from rapidocr import RapidOCR

        self._engine = RapidOCR(
            params={
                "Global.log_level": "critical",
                # The default scales a band's *short* side up to 736 px, so a
                # 1920x140 strip became ~10,000 px of detector input: slower,
                # and worse on the holdout than capping the long side.
                "Det.limit_type": "max",
                "Det.limit_side_len": det_side,
                "EngineConfig.onnxruntime.intra_op_num_threads": threads,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            }
        )
        self._lock = threading.Lock()

    def find(self, image: np.ndarray) -> list[tuple[str, Box]]:
        # Every flag is passed on every call: RapidOCR keeps the last call's
        # flags, so a recognition-only call left later detections disabled.
        with self._lock:
            result = self._engine(image, use_det=True, use_cls=False, use_rec=True)
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        if boxes is None or not texts:
            return []
        found: list[tuple[str, Box]] = []
        for text, polygon in zip(texts, boxes, strict=False):
            x0, y0 = np.asarray(polygon).min(axis=0)
            x1, y1 = np.asarray(polygon).max(axis=0)
            found.append((str(text), (int(x0), int(y0), int(x1), int(y1))))
        return found

    def read(self, image: np.ndarray) -> str | None:
        with self._lock:
            result = self._engine(image, use_det=False, use_cls=False, use_rec=True)
        texts = getattr(result, "txts", None)
        return str(texts[0]) if texts else None


_shared_engine: TextEngine | None = None
_shared_engine_lock = threading.Lock()


def _default_engine() -> TextEngine:
    global _shared_engine
    with _shared_engine_lock:
        if _shared_engine is None:
            _shared_engine = PaddleTextEngine()
        return _shared_engine


@dataclass(frozen=True, slots=True)
class _ClockBox:
    """Where a camera prints its clock, as fractions of the frame (y0, y1,
    x0, x1), so a resolution change does not lose it."""

    region: tuple[float, float, float, float]


def _clock_lines(lines: list[tuple[str, Box]]) -> tuple[str, Box] | None:
    """The clock among a band's text lines: the line holding a time, plus
    neighbours on the same row that belong to it — a date printed as its own
    box, AM/PM, a weekday. Camera names stay out, so the remembered box is
    the clock alone. Returns the clock's text, left to right, and its box."""
    anchor = next((line for line in lines if _TIME_LIKE.search(line[0])), None)
    if anchor is None:
        return None
    _, (ax0, ay0, ax1, ay1) = anchor
    height = max(1, ay1 - ay0)
    row = [
        line
        for line in lines
        if abs((line[1][1] + line[1][3]) / 2 - (ay0 + ay1) / 2) <= height * 0.6
        and (_DIGITS.search(line[0]) or _COMPANION.match(line[0].strip()))
    ]
    row.sort(key=lambda line: line[1][0])
    # Grow outwards from the anchor while the next box is close: a clock's
    # parts sit a few characters apart, a camera name further away.
    members = [anchor]
    x0, x1 = ax0, ax1
    index = row.index(anchor)
    for step in (1, -1):
        k = index + step
        while 0 <= k < len(row):
            bx0, _, bx1, _ = row[k][1]
            gap = bx0 - x1 if step == 1 else x0 - bx1
            if gap > height * 2.5:
                break
            members.append(row[k])
            x0, x1 = min(x0, bx0), max(x1, bx1)
            k += step
    members.sort(key=lambda line: line[1][0])
    text = " ".join(line[0] for line in members)
    y0 = min(line[1][1] for line in members)
    y1 = max(line[1][3] for line in members)
    return text, (x0, y0, x1, y1)


@dataclass(frozen=True, slots=True)
class _Reading:
    pts_ms: float
    value: datetime


@dataclass
class FrameClockReader:
    """Reads the burned-in clock from frames of one camera.

    `observe()` is called for every analysed frame and reads the overlay at
    most once per second of stream time — it only changes once a second, and
    OCR on every frame would be 25x the cost for the same information. With
    `eager=True` (a vehicle is in shot, so this frame may become evidence) it
    reads every frame it is given. `read_now()` reads one specific frame
    regardless. `verified()` answers for a frame whose clock was read: its
    reading, if another reading agrees.
    """

    tz: timezone = IST
    # The OCR models; None means the process-wide PP-OCRv6 engine, loaded on
    # first use.
    engine: TextEngine | None = None
    # Two readings agree when they differ by the footage between them, give or
    # take this much: the overlay ticks once a second, and a frame can sit
    # anywhere within its second. Replayed across the grid, 2 s rejected a
    # quarter of the inconsistent readings 3 s let through, for about one
    # point of coverage (evidence/CLOCK-READER-ACCURACY.md).
    agreement_tolerance_s: float = 2.0
    # Readings further apart than this in the footage are not compared.
    agreement_window_s: float = 300.0
    # A confirming reading must come from a later or earlier tick of the
    # overlay. Two frames a fraction of a second apart show the same digits,
    # damaged the same way by the same compression block, and read the same
    # wrong value: found on the grid, where frames 40 ms apart confirmed
    # each other's misread. They are one observation, not two.
    min_confirmation_gap_s: float = 0.9
    # A camera clock running a little fast is a camera clock. A year misread
    # as 2036 is not — and is the reading this bound exists to catch.
    max_future_skew_s: float = 86_400.0
    max_age_years: int = 5
    # A camera whose overlay has never been read pays for detection over the
    # frame's edges before giving up. Paid once a second for nothing, that is
    # real load, so it backs off. Once a camera's clock has been found,
    # failures are cheap (the remembered box only) and it keeps trying every
    # second.
    failure_backoff_after: int = 5
    failure_backoff_s: float = 30.0
    # A camera that has been read is still fully re-scanned this often after a
    # failure, in case its overlay moved or the remembered box stopped working.
    full_scan_interval_s: float = 30.0
    # Reads run inline in the camera's analysis loop, so eager reads are
    # capped per second of stream time.
    max_reads_per_second: int = 2
    history: int = 64

    _readings: deque[_Reading] = field(init=False)
    _preferred: _ClockBox | None = field(default=None, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _next_attempt_second: int = field(default=-1, init=False)
    _last_read_second: int | None = field(default=None, init=False)
    _reads_this_second: int = field(default=0, init=False)
    _last_full_scan_s: float | None = field(default=None, init=False)
    _scan_all: bool = field(default=True, init=False)
    _unavailable_logged: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._readings = deque(maxlen=self.history)

    def observe(self, frame: np.ndarray, *, pts_ms: float, eager: bool = False) -> datetime | None:
        """Read the overlay on this frame if this second has not been read
        yet — or, when `eager`, regardless. Returns the raw reading recorded
        for exactly this frame (not yet verified — see `verified()`), or None."""
        second = int(pts_ms // 1000)
        if second < self._next_attempt_second:
            return None
        if second == self._last_read_second:
            if not eager or self._reads_this_second >= self.max_reads_per_second:
                return None
            self._reads_this_second += 1
        else:
            self._last_read_second = second
            self._reads_this_second = 1
        return self._attempt(frame, pts_ms)

    def read_now(self, frame: np.ndarray, *, pts_ms: float) -> datetime | None:
        """Read the overlay on exactly this frame, outside the once-a-second
        rhythm — for the frame a sighting or zone event is attached to. A
        camera still in failure backoff is not re-tried. Returns the raw
        reading, or None."""
        existing = self._reading_at(pts_ms)
        if existing is not None:
            return existing.value
        if int(pts_ms // 1000) < self._next_attempt_second:
            return None
        return self._attempt(frame, pts_ms)

    def verified(self, pts_ms: float) -> datetime | None:
        """The clock read on the frame at `pts_ms`, if another reading of
        this camera's clock — on a different frame, within the agreement
        window — agrees with it after allowing for the footage between them.
        None otherwise: never read, or read but unconfirmed."""
        reading = self._reading_at(pts_ms)
        if reading is None:
            return None
        for other in self._readings:
            if other.pts_ms == reading.pts_ms:
                continue
            footage_s = (reading.pts_ms - other.pts_ms) / 1000.0
            if not self.min_confirmation_gap_s <= abs(footage_s) <= self.agreement_window_s:
                continue
            clock_s = (reading.value - other.value).total_seconds()
            if abs(clock_s - footage_s) <= self.agreement_tolerance_s:
                return reading.value
        return None

    def reset(self) -> None:
        """The stream's timeline restarted (a reconnect or a loop point): its
        PTS origin moved, so readings before and after cannot be compared."""
        self._readings.clear()
        self._last_read_second = None
        self._next_attempt_second = -1
        self._last_full_scan_s = None

    def _reading_at(self, pts_ms: float) -> _Reading | None:
        for reading in reversed(self._readings):
            if reading.pts_ms == pts_ms:
                return reading
        return None

    def _attempt(self, frame: np.ndarray, pts_ms: float) -> datetime | None:
        now_s = pts_ms / 1000.0
        self._scan_all = self._preferred is None or (
            self._last_full_scan_s is None
            or now_s - self._last_full_scan_s >= self.full_scan_interval_s
        )
        if self._scan_all:
            self._last_full_scan_s = now_s
        text = self._ocr(frame)
        parsed = parse_overlay_timestamp(text, tz=self.tz) if text is not None else None
        if parsed is None or not self._is_plausible(parsed):
            self._consecutive_failures += 1
            if self._preferred is None and self._consecutive_failures >= self.failure_backoff_after:
                self._next_attempt_second = int(now_s + self.failure_backoff_s)
            return None
        self._consecutive_failures = 0
        self._next_attempt_second = -1
        self._readings.append(_Reading(pts_ms=pts_ms, value=parsed))
        return parsed

    def _is_plausible(self, value: datetime) -> bool:
        """Reject values that cannot be a recording's capture time.

        The decisive one is the future: footage cannot have been captured
        after we processed it. A camera clock can run fast, so the bound is a
        day rather than seconds — wide enough for a mis-set clock, tight
        enough to catch a year read as 2036 instead of 2026, which otherwise
        parses perfectly and looks entirely reasonable.
        """
        now = datetime.now(UTC)
        if value > now + timedelta(seconds=self.max_future_skew_s):
            return False
        return value >= now - timedelta(days=365 * self.max_age_years)

    def _ocr(self, frame: np.ndarray) -> str | None:
        """Text of the camera's clock on this frame, if it parses to a
        plausible timestamp.

        The fleet does not share one overlay layout: top-left, top-right,
        bottom-left; day-first or year-first; weekday and AM/PM in various
        places. Detection over the frame's top and bottom edges finds it;
        the box is then remembered and only recognition runs on it. The full
        scan runs until a box is found, and periodically after a failure in
        case the overlay moved.
        """
        engine = self._engine()
        if engine is None:
            return None
        height, width = frame.shape[:2]
        try:
            if self._preferred is not None and not self._scan_all:
                y0, y1, x0, x1 = self._preferred.region
                crop = frame[int(height * y0) : int(height * y1), int(width * x0) : int(width * x1)]
                text = engine.read(crop) if crop.size else None
                return text if text is not None and self._parses(text) else None
            for band_y0, band_y1 in _BANDS:
                top = int(height * band_y0)
                band = frame[top : max(top + 1, int(height * band_y1))]
                clock = _clock_lines(engine.find(band))
                if clock is None or not self._parses(clock[0]):
                    continue
                text, (bx0, by0, bx1, by1) = clock
                margin = int((by1 - by0) * _BOX_MARGIN) + 1
                self._preferred = _ClockBox(
                    (
                        max(0, top + by0 - margin) / height,
                        min(height, top + by1 + margin) / height,
                        max(0, bx0 - margin) / width,
                        min(width, bx1 + margin) / width,
                    )
                )
                return text
        except Exception as exc:  # pragma: no cover - a broken runtime, not a frame
            self._warn_once(f"OCR failed: {exc}")
            return None
        return None

    def _parses(self, text: str) -> bool:
        parsed = parse_overlay_timestamp(text, tz=self.tz)
        return parsed is not None and self._is_plausible(parsed)

    def _engine(self) -> TextEngine | None:
        if self.engine is not None:
            return self.engine
        try:
            self.engine = _default_engine()
        except Exception as exc:  # pragma: no cover - depends on the environment
            self._warn_once(f"the OCR models could not load: {exc}")
            return None
        return self.engine

    def _warn_once(self, reason: str) -> None:
        if self._unavailable_logged:
            return
        self._unavailable_logged = True
        logger.warning(
            "cannot read the camera's burned-in timestamp (%s) — this camera's "
            "sightings will be recorded with time unknown",
            reason,
        )
