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

Deliberately degrades rather than guesses. If Tesseract is not installed, if
no corner of the frame holds a readable clock, or if nothing agrees with a
reading, the answer is None and the sighting is recorded as "time unknown".
An evidence trail with a confidently wrong time is worse than one that admits
it does not know.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

import cv2
import numpy as np

__all__ = ["IST", "FrameClockReader", "parse_overlay_timestamp"]

# Letters are allowed on purpose: several cameras print a weekday between
# the date and the time ("13-06-2026 Sat 21:01:53") or AM/PM after it, and
# excluding letters made Tesseract render them as digit noise that corrupted
# the numbers either side. The parser skips what it does not need.
_TESSERACT_CONFIG = (
    "--psm {psm} -c tessedit_char_whitelist="
    "0123456789-/: ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)

logger = logging.getLogger(__name__)

# Gujarat. The overlay is the camera's local wall clock with no zone marker,
# so the offset has to come from somewhere — configured rather than guessed,
# and applied explicitly so the stored UTC value is auditable.
IST = timezone(timedelta(hours=5, minutes=30))

# Tolerant on purpose. Tesseract reliably reads the digits of these OSD fonts
# but drops separators unpredictably — real observed output includes
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


@dataclass(frozen=True, slots=True)
class _Attempt:
    """One way of looking for the overlay: a region of the frame (fractions
    of height and width, so it holds across 720p, 1080p and 1440p), whether
    to binarise it, and Tesseract's page segmentation mode — 7 reads one line,
    11 finds sparse text anywhere in the crop."""

    region: tuple[float, float, float, float]  # y0, y1, x0, x1
    binarise: bool
    psm: int


_TOP_LEFT_TIGHT = (0.0, 0.075, 0.0, 0.45)
_TOP_LEFT = (0.0, 0.12, 0.0, 0.60)
_TOP_RIGHT = (0.0, 0.13, 0.40, 1.0)
_BOTTOM_LEFT = (0.87, 1.0, 0.0, 0.60)
_BOTTOM_RIGHT = (0.87, 1.0, 0.40, 1.0)

# Tightest top-left first, as before: a crop larger than the overlay drags in
# scene content, and the same cam06 frame that reads correctly in a tight crop
# returned the year as 2036 in a looser one. The other corners and sparse-text
# mode come after; each was needed by at least one camera on the government
# grid (overlays top-right, bottom-left, and amid a camera name).
_ATTEMPTS: tuple[_Attempt, ...] = (
    _Attempt(_TOP_LEFT_TIGHT, binarise=True, psm=7),
    _Attempt(_TOP_LEFT_TIGHT, binarise=False, psm=7),
    _Attempt(_TOP_LEFT, binarise=True, psm=7),
    _Attempt(_TOP_LEFT, binarise=False, psm=7),
    _Attempt(_TOP_LEFT, binarise=True, psm=11),
    _Attempt(_TOP_RIGHT, binarise=True, psm=7),
    _Attempt(_TOP_RIGHT, binarise=True, psm=11),
    _Attempt(_BOTTOM_LEFT, binarise=True, psm=7),
    _Attempt(_BOTTOM_RIGHT, binarise=True, psm=7),
)


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
    # Tuned on real frames from the fleet's resolutions; the OSD is near-white.
    threshold: int = 160
    # Two readings agree when they differ by the footage between them, give or
    # take this much: the overlay ticks once a second, and a frame can sit
    # anywhere within its second.
    agreement_tolerance_s: float = 3.0
    # Readings further apart than this in the footage are not compared.
    agreement_window_s: float = 300.0
    # A camera clock running a little fast is a camera clock. A year misread
    # as 2036 is not — and is the reading this bound exists to catch.
    max_future_skew_s: float = 86_400.0
    max_age_years: int = 5
    # A camera whose overlay has never been read pays for every region and
    # variant before giving up. Paid once a second for nothing, that is real
    # load, so it backs off. Once a camera's overlay has been found, failures
    # are cheap (the remembered attempt only) and it keeps trying every second.
    failure_backoff_after: int = 5
    failure_backoff_s: float = 30.0
    # A camera that has been read is still fully re-scanned this often after a
    # failure, in case its overlay moved or the remembered crop stopped working.
    full_scan_interval_s: float = 30.0
    # Between full scans, this many of the camera's most successful attempts
    # are tried. One crop can misread a camera's year systematically (2026 as
    # 2036) where another reads it every time, so one is not enough.
    ranked_attempts: int = 2
    # Each read is a Tesseract process (about 100 ms on a loaded laptop) run
    # inline in the camera's analysis loop, so eager reads are capped per
    # second of stream time.
    max_reads_per_second: int = 2
    history: int = 64

    _readings: deque[_Reading] = field(init=False)
    _preferred: _Attempt | None = field(default=None, init=False)
    _successes: Counter[_Attempt] = field(default_factory=Counter, init=False)
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
            if abs(footage_s) > self.agreement_window_s:
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
        """Text of the first attempt whose output parses to a plausible
        timestamp.

        The fleet does not share one overlay layout: top-left, top-right,
        bottom-left; day-first or year-first; weekday and AM/PM in various
        places. Every attempt shells out to Tesseract, so a camera's working
        attempt is remembered and tried alone; the full list runs only until
        one is found, and periodically after a failure in case it moved.
        """
        try:
            import pytesseract
        except ImportError:  # pragma: no cover - depends on the environment
            self._warn_once("pytesseract is not installed")
            return None

        ranked = sorted(_ATTEMPTS, key=lambda a: -self._successes[a])
        attempts: tuple[_Attempt, ...]
        if self._preferred is not None and not self._scan_all:
            attempts = tuple(a for a in ranked[: self.ranked_attempts] if self._successes[a])
        else:
            attempts = tuple(ranked)

        height, width = frame.shape[:2]
        for attempt in attempts:
            y0, y1, x0, x1 = attempt.region
            crop = frame[
                int(height * y0) : max(1, int(height * y1)), int(width * x0) : int(width * x1)
            ]
            if crop.size == 0:
                continue
            image = self._prepare(crop, binarise=attempt.binarise, upscale=height < 900)
            try:
                text = str(
                    pytesseract.image_to_string(
                        image, config=_TESSERACT_CONFIG.format(psm=attempt.psm)
                    )
                )
            except Exception as exc:  # pragma: no cover - binary missing/broken
                self._warn_once(f"tesseract failed: {exc}")
                return None
            parsed = parse_overlay_timestamp(text, tz=self.tz)
            if parsed is not None and self._is_plausible(parsed):
                self._successes[attempt] += 1
                self._preferred = self._successes.most_common(1)[0][0]
                return text
        return None

    def _prepare(self, crop: np.ndarray, *, binarise: bool, upscale: bool) -> np.ndarray:
        grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        # Sub-1080p frames carry small overlay glyphs, below what Tesseract
        # reads reliably; upscaling the crop recovers them.
        if upscale:
            grey = cv2.resize(grey, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        if not binarise:
            return grey
        # The OSD is light text with a dark outline over arbitrary scene
        # content, so a fixed high threshold isolates it better than Otsu,
        # which picks its level from the whole crop and lets the scene
        # dominate. PSM 7 reads a single text *line* and does badly when
        # glyphs touch the image edge, hence the border.
        binary = cv2.threshold(grey, self.threshold, 255, cv2.THRESH_BINARY)[1]
        return cv2.copyMakeBorder(binary, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=0)

    def _warn_once(self, reason: str) -> None:
        if self._unavailable_logged:
            return
        self._unavailable_logged = True
        logger.warning(
            "cannot read the camera's burned-in timestamp (%s) — this camera's "
            "sightings will be recorded with time unknown",
            reason,
        )
