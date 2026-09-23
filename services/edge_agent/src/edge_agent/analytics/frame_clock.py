"""Reading the camera's own clock off the frame.

The government cameras burn a timestamp into the top-left of every frame:

    17-06-2026 18:04:42

That is the *camera's* record of when the footage was captured, and for an
evidence system it is the only timestamp that means anything in a courtroom.
Everything else we could use is a statement about us, not about the scene.

This matters more than it sounds. The grid replays continuous recordings, so
a detection processed today can be of footage recorded in June — and
`StreamClock`, which anchors PTS to wall-clock at connection (ADR-005),
will happily stamp it with today's date. That is correct for measuring
latency and pipeline behaviour, and wrong for saying when a vehicle was
somewhere. Both timestamps are kept for exactly that reason: `observed_at`
becomes the camera's own time when we can read it, and the PTS-derived time
stays available as the processing clock.

Deliberately degrades rather than guesses. If Tesseract is not installed, if
the crop holds no readable clock, or if the parsed value is implausible, this
returns None and the caller keeps the PTS-derived timestamp. An evidence
trail with a confidently wrong time is worse than one that admits it only
knows when it processed something.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

import cv2
import numpy as np

__all__ = ["FrameClockReader", "parse_overlay_timestamp"]

logger = logging.getLogger(__name__)

# Gujarat. The overlay is the camera's local wall clock with no zone marker,
# so the offset has to come from somewhere — configured rather than guessed,
# and applied explicitly so the stored UTC value is auditable.
IST = timezone(timedelta(hours=5, minutes=30))

# Tolerant on purpose. Tesseract reliably reads the digits of this OSD font
# but drops separators unpredictably — real observed output includes
# "17-06-202618:04:42" and "13-06-2026 2102:28". The digits are what matter.
_TIMESTAMP_RE = re.compile(
    r"(?P<day>\d{2})\D?(?P<month>\d{2})\D?(?P<year>\d{4})"
    r"\D*?"
    r"(?P<hour>\d{2})\D?(?P<minute>\d{2})\D?(?P<second>\d{2})"
)


def parse_overlay_timestamp(text: str, *, tz: timezone = IST) -> datetime | None:
    """Parse a `DD-MM-YYYY HH:MM:SS` overlay, tolerating dropped separators.

    Returns an aware UTC datetime, or None when the text holds no plausible
    timestamp — including values that parse but cannot be real, which is how
    a misread digit shows up.
    """
    match = _TIMESTAMP_RE.search(text)
    if match is None:
        return None
    try:
        local = datetime(
            year=int(match["year"]),
            month=int(match["month"]),
            day=int(match["day"]),
            hour=int(match["hour"]),
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


@dataclass
class FrameClockReader:
    """Reads the burned-in clock from frames of one camera.

    `crop_height`/`crop_width` are fractions of the frame, not pixels: the
    fleet runs at 1920x1080 and 1280x720 and the overlay scales with the
    frame, so a pixel box tuned on one resolution silently misses on the
    other.

    Results are cached per second of stream time. The overlay only changes
    once a second, and OCR is far too expensive to run on every frame of
    every camera — at 25fps that would be 25x the work for 1x the
    information.
    """

    crop_height: float = 0.075
    crop_width: float = 0.45
    tz: timezone = IST
    # Tuned on real frames from both fleet resolutions; the OSD is near-white.
    threshold: int = 160
    # A reading that jumps further than this from the last one is a misread,
    # not a real jump — OCR inserting a digit turns 21:02 into 21:10.
    max_jump_s: float = 600.0
    # Two readings this close together corroborate each other, which is
    # what lets a wrong anchor be overturned.
    corroboration_s: float = 120.0
    # A camera clock can run slightly ahead of ours; a year cannot.
    max_future_skew_s: float = 300.0
    max_age_years: int = 5

    _anchor: datetime | None = None
    _candidate: datetime | None = None
    _last_read_second: int | None = None
    _unavailable_logged: bool = False

    def read(self, frame: np.ndarray, *, pts_ms: float | None = None) -> datetime | None:
        """The camera's own timestamp for this frame, or None.

        `pts_ms` drives the once-a-second cache. Without it every call runs
        OCR, which is correct but wasteful — callers in a frame loop should
        pass it.
        """
        if pts_ms is not None:
            second = int(pts_ms // 1000)
            if second == self._last_read_second:
                return self._anchor
            self._last_read_second = second

        text = self._ocr(frame)
        if text is None:
            return self._anchor
        parsed = parse_overlay_timestamp(text, tz=self.tz)
        if parsed is None or not self._is_plausible(parsed):
            return self._anchor

        drift = (
            abs((parsed - self._anchor).total_seconds()) if self._anchor is not None else None
        )
        if drift is not None and drift <= self.max_jump_s:
            # Consistent with what we already trust: the normal case.
            self._anchor = parsed
            self._candidate = None
            return self._anchor

        # Either nothing is trusted yet, or this disagrees with the anchor.
        # A single reading is not enough to establish or overturn one — one
        # inserted digit produces a confident, wrong value. But neither can a
        # bad anchor be allowed to stand forever: an earlier version rejected
        # every *correct* reading as a jump once it had locked onto a misread,
        # and the timestamp froze. So a second, agreeing reading promotes the
        # candidate and the clock self-heals.
        if self._candidate is not None and abs(
            (parsed - self._candidate).total_seconds()
        ) <= self.corroboration_s:
            self._anchor = parsed
            self._candidate = None
        else:
            self._candidate = parsed
        return self._anchor

    def _is_plausible(self, value: datetime) -> bool:
        """Reject values that cannot be a recording's capture time.

        The decisive one is the future: footage cannot have been captured
        after we processed it, so a camera clock ahead of now is a misread.
        This is what catches a year read as 2036 instead of 2026 — which
        otherwise parses perfectly and looks entirely reasonable.
        """
        now = datetime.now(UTC)
        if value > now + timedelta(seconds=self.max_future_skew_s):
            return False
        return value >= now - timedelta(days=365 * self.max_age_years)

    def _ocr(self, frame: np.ndarray) -> str | None:
        try:
            import pytesseract
        except ImportError:  # pragma: no cover - depends on the environment
            self._warn_once("pytesseract is not installed")
            return None

        height, width = frame.shape[:2]
        crop = frame[
            : max(1, int(height * self.crop_height)), : max(1, int(width * self.crop_width))
        ]
        if crop.size == 0:
            return None
        grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop

        # Two attempts, cheapest-and-best first. The OSD is white text with a
        # dark outline, so a fixed high threshold isolates it cleanly from
        # almost any scene — Otsu, which picks its level from the whole crop,
        # was measurably worse because the scene behind the text dominates it.
        # The border matters: PSM 7 reads a single text *line* and does badly
        # when glyphs touch the image edge. Plain greyscale is the fallback
        # for scenes bright enough to wash the threshold out.
        binary = cv2.threshold(grey, self.threshold, 255, cv2.THRESH_BINARY)[1]
        padded = cv2.copyMakeBorder(binary, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=0)

        for candidate in (padded, grey):
            try:
                text = str(
                    pytesseract.image_to_string(
                        candidate,
                        config="--psm 7 -c tessedit_char_whitelist=0123456789-: ",
                    )
                )
            except Exception as exc:  # pragma: no cover - binary missing/broken
                self._warn_once(f"tesseract failed: {exc}")
                return None
            if _TIMESTAMP_RE.search(text):
                return text
        return None

    def _warn_once(self, reason: str) -> None:
        if self._unavailable_logged:
            return
        self._unavailable_logged = True
        logger.warning(
            "cannot read the camera's burned-in timestamp (%s) — falling back to "
            "PTS-derived times, which record when WE processed the frame, not when "
            "the camera captured it",
            reason,
        )
