"""Tests for reading the camera's burned-in clock.

The parsing cases here are not invented: every malformed string below is
real OCR output observed against frames from the government grid (from the
Tesseract reader this replaced and from PP-OCRv6). The OSD font reads
reliably digit-by-digit and drops separators unpredictably, so tolerating
that is the whole job. The OCR models themselves are stood in for by a fake
engine; their accuracy is measured on real frames by scripts/eval_clock.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from edge_agent.analytics.frame_clock import (
    IST,
    FrameClockReader,
    _clock_lines,
    _ClockBox,
    parse_overlay_timestamp,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Every malformed form here is real OCR output from grid frames.
        ("17-06-2026 18:04:42", (2026, 6, 17, 12, 34, 42)),
        ("17-06-202618:04:42", (2026, 6, 17, 12, 34, 42)),  # date/time run together
        ("13-06-2026 2102:28", (2026, 6, 13, 15, 32, 28)),  # a dropped colon
        ("  17-06-2026  18:04:42  ", (2026, 6, 17, 12, 34, 42)),
    ],
)
def test_separators_are_optional(text: str, expected: tuple[int, ...]) -> None:
    """OCR drops separators from this OSD font unpredictably; the
    digits are what carry the meaning."""
    parsed = parse_overlay_timestamp(text)
    assert parsed is not None
    assert (
        parsed.year,
        parsed.month,
        parsed.day,
        parsed.hour,
        parsed.minute,
        parsed.second,
    ) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Real layouts observed across the fleet — they do not agree.
        ("13-06-2026 Sat 21:01:53", (2026, 6, 13, 15, 31, 53)),  # weekday mid-string
        ("13/06/2026 21:01:32 Sat", (2026, 6, 13, 15, 31, 32)),  # slashes, weekday last
        ("17-06-2026 18:04:42", (2026, 6, 17, 12, 34, 42)),
        ("2026-08-03 Mon 21:00:43", (2026, 8, 3, 15, 30, 43)),  # year first
        ("08/08/2026 23:20:53", (2026, 8, 8, 17, 50, 53)),
        ("14-06-2026 12:00:30 AM", (2026, 6, 13, 18, 30, 30)),  # midnight, 12-hour clock
        ("13-06-2026 09:00:19 PM", (2026, 6, 13, 15, 30, 19)),
        ("Delthali Char Rasta 14-06-2026 00:44:52", (2026, 6, 13, 19, 14, 52)),  # after a name
    ],
)
def test_the_fleets_different_overlay_layouts_all_parse(
    text: str, expected: tuple[int, ...]
) -> None:
    """Cameras print a weekday in different places and some use slashes. The
    parser keys off the digits and skips whatever sits between them."""
    parsed = parse_overlay_timestamp(text)
    assert parsed is not None
    assert (
        parsed.year,
        parsed.month,
        parsed.day,
        parsed.hour,
        parsed.minute,
        parsed.second,
    ) == expected


def test_the_overlay_is_local_time_and_is_stored_as_utc() -> None:
    """The camera stamps its own wall clock with no zone marker. Gujarat is
    UTC+5:30, so 18:04:42 IST is 12:34:42 UTC — applied explicitly rather
    than left ambiguous."""
    parsed = parse_overlay_timestamp("17-06-2026 18:04:42")
    assert parsed == datetime(2026, 6, 17, 12, 34, 42, tzinfo=UTC)
    assert parsed.tzinfo is UTC


def test_a_different_zone_can_be_configured() -> None:
    parsed = parse_overlay_timestamp("17-06-2026 18:04:42", tz=UTC)
    assert parsed == datetime(2026, 6, 17, 18, 4, 42, tzinfo=UTC)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no digits here",
        "17-06-2026",  # date with no time
        "32-06-2026 18:04:42",  # impossible day, from a misread digit
        "17-16-2026 18:04:42",  # impossible month
        "17-06-2026 28:04:42",  # impossible hour
        "17-06-1026 18:04:42",  # implausible year
        "13-06-2026 13:00:19 PM",  # no 13 o'clock on a 12-hour clock
    ],
)
def test_unreadable_or_impossible_values_return_none(text: str) -> None:
    """A wrong timestamp in an evidence trail is worse than no timestamp, so
    anything that cannot be real is refused rather than clamped."""
    assert parse_overlay_timestamp(text) is None


def test_ist_is_five_and_a_half_hours() -> None:
    assert IST.utcoffset(None) == timedelta(hours=5, minutes=30)


def _blank_frame() -> np.ndarray:
    return np.zeros((720, 1280, 3), dtype=np.uint8)


class _NoEngine:
    """An OCR engine that sees no text: a camera with no clock."""

    def find(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int]]]:
        return []

    def read(self, image: np.ndarray) -> str | None:
        return None


class _FakeEngine:
    """Detection finds `lines` (text and box, in the band's pixels) in the
    top band; recognising a cropped box returns `box_text`. Counts calls."""

    def __init__(
        self, lines: list[tuple[str, tuple[int, int, int, int]]], box_text: str | None
    ) -> None:
        self.lines = lines
        self.box_text = box_text
        self.finds = 0
        self.reads = 0

    def find(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int]]]:
        self.finds += 1
        # Only the top band of a 720p frame (93 px) holds the overlay.
        return self.lines if image.shape[0] < 100 and self.finds % 2 == 1 else []

    def read(self, image: np.ndarray) -> str | None:
        self.reads += 1
        return self.box_text


def _reader_reading(texts: dict[int, str | None], **kwargs: float) -> FrameClockReader:
    """A reader whose OCR returns `texts[second]` for a frame at that second
    of stream time — the frame's own overlay, as the camera printed it."""
    reader = FrameClockReader(engine=_NoEngine(), **kwargs)  # type: ignore[arg-type]
    current: dict[str, int] = {"second": 0}

    def ocr(frame: np.ndarray) -> str | None:
        return texts.get(current["second"])

    original_attempt = reader._attempt

    def attempt(frame: np.ndarray, pts_ms: float) -> datetime | None:
        current["second"] = int(pts_ms // 1000)
        return original_attempt(frame, pts_ms)

    reader._ocr = ocr  # type: ignore[method-assign]
    reader._attempt = attempt  # type: ignore[method-assign]
    return reader


def _utc(text: str) -> datetime:
    parsed = parse_overlay_timestamp(text)
    assert parsed is not None
    return parsed


def test_a_frame_with_no_readable_clock_has_no_time() -> None:
    """A black frame has no overlay, so nothing is known about its time."""
    reader = FrameClockReader(engine=_NoEngine())
    assert reader.observe(_blank_frame(), pts_ms=1000.0) is None
    assert reader.verified(1000.0) is None


def test_the_overlay_is_read_at_most_once_per_stream_second() -> None:
    """The overlay changes once a second; OCR on every frame would be 25x
    the cost for the same answer."""
    reader = FrameClockReader(engine=_NoEngine())
    calls = 0

    def counting(frame: np.ndarray) -> str | None:
        nonlocal calls
        calls += 1
        return "17-06-2026 18:04:42"

    reader._ocr = counting  # type: ignore[method-assign]
    reader.observe(_blank_frame(), pts_ms=1000.0)
    reader.observe(_blank_frame(), pts_ms=1400.0)
    assert calls == 1, "OCR must not re-run within the same second of stream time"
    reader.observe(_blank_frame(), pts_ms=2100.0)
    assert calls == 2, "a new second should re-read the overlay"


def test_a_single_reading_is_never_enough() -> None:
    """One inserted digit turns 21:02 into 21:10 and parses perfectly. A
    reading nothing agrees with is not a time."""
    reader = _reader_reading({1: "17-06-2026 18:04:42"})
    assert reader.observe(_blank_frame(), pts_ms=1000.0) == _utc("17-06-2026 18:04:42")
    assert reader.verified(1000.0) is None


def test_two_readings_that_agree_with_the_footage_confirm_each_other() -> None:
    """Three seconds of footage, three seconds on the clock: both readings
    are the camera's time, and each frame keeps its own."""
    reader = _reader_reading({1: "17-06-2026 18:04:42", 4: "17-06-2026 18:04:45"})
    reader.observe(_blank_frame(), pts_ms=1000.0)
    reader.observe(_blank_frame(), pts_ms=4000.0)
    assert reader.verified(1000.0) == _utc("17-06-2026 18:04:42")
    assert reader.verified(4000.0) == _utc("17-06-2026 18:04:45")


def test_a_misread_between_good_readings_is_refused_and_does_not_block_them() -> None:
    """The misread disagrees with both neighbours, so it is never used — and
    the good readings either side still confirm each other across it."""
    reader = _reader_reading(
        {1: "17-06-2026 18:04:42", 2: "17-06-2026 18:10:43", 3: "17-06-2026 18:04:44"}
    )
    for second in (1, 2, 3):
        reader.observe(_blank_frame(), pts_ms=second * 1000.0)
    assert reader.verified(2000.0) is None
    assert reader.verified(1000.0) == _utc("17-06-2026 18:04:42")
    assert reader.verified(3000.0) == _utc("17-06-2026 18:04:44")


def test_when_the_footage_jumps_the_clock_jumps_with_it() -> None:
    """A stitched recording cuts from 21:01 to 21:10 in five seconds of
    footage. Readings after the cut agree with each other, so they are the
    camera's time — no reading is ever projected across the cut."""
    reader = _reader_reading(
        {
            1: "08-08-2026 21:01:50",
            2: "08-08-2026 21:01:51",
            6: "08-08-2026 21:10:37",
            7: "08-08-2026 21:10:38",
        }
    )
    for second in (1, 2, 6, 7):
        reader.observe(_blank_frame(), pts_ms=second * 1000.0)
    assert reader.verified(2000.0) == _utc("08-08-2026 21:01:51")
    assert reader.verified(6000.0) == _utc("08-08-2026 21:10:37")


def test_a_frame_cannot_confirm_itself() -> None:
    """Reading the same frame twice repeats any misread; agreement has to
    come from a different frame."""
    reader = _reader_reading({1: "17-06-2026 18:04:42"})
    reader.observe(_blank_frame(), pts_ms=1000.0)
    assert reader.read_now(_blank_frame(), pts_ms=1000.0) == _utc("17-06-2026 18:04:42")
    assert reader.verified(1000.0) is None


def test_read_now_reads_a_frame_the_once_a_second_rhythm_skipped() -> None:
    """A sighting's own frame may fall in a second already read; its clock
    is still read, and confirmed by the previous second's reading."""
    reader = _reader_reading({0: "17-06-2026 18:04:41", 1: "17-06-2026 18:04:42"})
    reader.observe(_blank_frame(), pts_ms=400.0)
    reader.observe(_blank_frame(), pts_ms=1000.0)
    assert reader.observe(_blank_frame(), pts_ms=1500.0) is None
    assert reader.read_now(_blank_frame(), pts_ms=1500.0) == _utc("17-06-2026 18:04:42")
    assert reader.verified(1500.0) == _utc("17-06-2026 18:04:42")


def test_frames_of_one_overlay_tick_do_not_confirm_each_other() -> None:
    """Found on the grid: frames 40 ms apart show the same digits, damaged
    the same way by the same compression block, and the model read the
    same wrong second on both. They are one observation, so neither
    confirms the other; a reading from another tick is needed."""
    reader = _reader_reading({1: "03-08-2026 21:05:15"})
    reader.observe(_blank_frame(), pts_ms=1000.0)
    reader.read_now(_blank_frame(), pts_ms=1040.0)
    assert reader.verified(1000.0) is None
    assert reader.verified(1040.0) is None


def test_readings_too_far_apart_are_not_compared() -> None:
    reader = _reader_reading(
        {1: "17-06-2026 18:04:42", 400: "17-06-2026 18:11:21"}, agreement_window_s=300.0
    )
    reader.observe(_blank_frame(), pts_ms=1000.0)
    reader.observe(_blank_frame(), pts_ms=400_000.0)
    assert reader.verified(400_000.0) is None


def test_reset_forgets_readings_from_the_previous_timeline() -> None:
    """After a reconnect or loop point the PTS origin moves, so footage
    between old and new readings can no longer be measured."""
    reader = _reader_reading({1: "17-06-2026 18:04:42", 2: "17-06-2026 18:04:43"})
    reader.observe(_blank_frame(), pts_ms=1000.0)
    reader.reset()
    reader.observe(_blank_frame(), pts_ms=2000.0)
    assert reader.verified(2000.0) is None


def test_a_year_misread_into_the_future_is_refused() -> None:
    """Found in production: a year misread as 2036 instead of 2026 parses
    perfectly. Footage cannot be captured after it was processed."""
    future = datetime.now(UTC).astimezone(IST) + timedelta(days=3650)
    text = future.strftime("%d-%m-%Y %H:%M:%S")
    reader = _reader_reading({1: text, 2: text})
    assert reader.observe(_blank_frame(), pts_ms=1000.0) is None
    assert reader.observe(_blank_frame(), pts_ms=2000.0) is None, "not even when repeated"


def test_a_camera_clock_running_fast_is_still_the_camera_clock() -> None:
    """A mis-set camera clock a couple of hours ahead is what the camera
    says, and what the camera says is final."""
    ahead = datetime.now(UTC).astimezone(IST) + timedelta(hours=2)
    reader = _reader_reading(
        {
            1: ahead.strftime("%d-%m-%Y %H:%M:%S"),
            2: (ahead + timedelta(seconds=1)).strftime("%d-%m-%Y %H:%M:%S"),
        }
    )
    reader.observe(_blank_frame(), pts_ms=1000.0)
    reader.observe(_blank_frame(), pts_ms=2000.0)
    assert reader.verified(2000.0) is not None


def test_an_absurdly_old_timestamp_is_refused() -> None:
    reader = _reader_reading({1: "17-06-1999 18:04:42"}, max_age_years=5)
    assert reader.observe(_blank_frame(), pts_ms=1000.0) is None


def test_a_camera_never_read_backs_off() -> None:
    """Each attempt on an unread camera runs text detection over the frame's
    edges. A camera whose overlay is unreadable would otherwise pay that every
    second forever, for no information."""
    reader = FrameClockReader(engine=_NoEngine(), failure_backoff_after=3, failure_backoff_s=30.0)
    attempts = 0

    def failing(frame: np.ndarray) -> str | None:
        nonlocal attempts
        attempts += 1
        return None

    reader._ocr = failing  # type: ignore[method-assign]
    for second in range(1, 11):
        reader.observe(_blank_frame(), pts_ms=second * 1000.0)
    assert attempts == 3, "should stop attempting once the failure threshold is hit"
    assert reader.read_now(_blank_frame(), pts_ms=10_500.0) is None
    assert attempts == 3, "read_now respects the backoff too"

    reader.observe(_blank_frame(), pts_ms=45_000.0)
    assert attempts == 4, "well past the backoff window, it tries again"


def test_a_camera_already_read_keeps_trying_every_second() -> None:
    """Once its overlay has been found, a failure is one cheap attempt, and
    a corrupted frame is no reason to stop reading the next one."""
    reader = FrameClockReader(engine=_NoEngine(), failure_backoff_after=2)
    reader._preferred = _ClockBox((0.0, 0.05, 0.0, 0.3))
    attempts = 0

    def failing(frame: np.ndarray) -> str | None:
        nonlocal attempts
        attempts += 1
        return None

    reader._ocr = failing  # type: ignore[method-assign]
    for second in range(1, 8):
        reader.observe(_blank_frame(), pts_ms=second * 1000.0)
    assert attempts == 7


def test_the_clock_box_is_remembered_and_only_recognised_after() -> None:
    """Detection runs until the clock is found; after that only its box is
    recognised, the cheap half of the models."""
    engine = _FakeEngine(
        [("17-06-2026 18:04:42", (10, 8, 300, 40))], box_text="17-06-2026 18:04:43"
    )
    reader = FrameClockReader(engine=engine, full_scan_interval_s=30.0)
    assert reader.observe(_blank_frame(), pts_ms=1000.0) is not None
    assert engine.finds >= 1 and engine.reads == 0
    assert reader._preferred is not None

    finds = engine.finds
    assert reader.observe(_blank_frame(), pts_ms=2000.0) is not None
    assert engine.finds == finds, "a known camera does not re-run detection"
    assert engine.reads == 1
    assert reader.verified(2000.0) is not None


def test_a_failing_box_falls_back_to_a_full_scan_in_time() -> None:
    """If the remembered box stops reading (the overlay moved), the camera
    is scanned in full again once the interval has passed."""
    engine = _FakeEngine([("17-06-2026 18:04:42", (10, 8, 300, 40))], box_text=None)
    reader = FrameClockReader(engine=engine, full_scan_interval_s=5.0)
    reader.observe(_blank_frame(), pts_ms=1000.0)
    finds = engine.finds
    reader.observe(_blank_frame(), pts_ms=2000.0)
    assert engine.finds == finds
    reader.observe(_blank_frame(), pts_ms=7000.0)
    assert engine.finds > finds


def test_eager_reads_more_often_while_a_vehicle_needs_evidence() -> None:
    """Any frame of a passing vehicle may become its evidence, so while one
    needs a clock frame the overlay is read more than once a second — up to
    a cap, because every read runs inline in the camera's analysis loop."""
    reader = FrameClockReader(engine=_NoEngine(), max_reads_per_second=2)
    calls = 0

    def counting(frame: np.ndarray) -> str | None:
        nonlocal calls
        calls += 1
        return "17-06-2026 18:04:42"

    reader._ocr = counting  # type: ignore[method-assign]
    for pts in (1000.0, 1250.0, 1500.0, 1750.0):
        reader.observe(_blank_frame(), pts_ms=pts, eager=True)
    assert calls == 2, "capped at max_reads_per_second"
    assert reader.verified(1250.0) is None, "frames of one overlay tick are one observation"
    reader.observe(_blank_frame(), pts_ms=2250.0, eager=True)
    assert reader.verified(1250.0) is not None, "the next tick confirms it"


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        # Real PP-OCRv6 detections on grid frames (band pixels).
        ([("13-06-2026 09:07:49 PM", (817, 26, 1237, 105))], "13-06-2026 09:07:49 PM"),
        # AM/PM as its own box: without it 09:07 PM parses as the morning.
        (
            [
                ("13-06-2026", (817, 26, 1013, 105)),
                ("09:07:49", (1014, 26, 1171, 105)),
                ("PM", (1172, 26, 1237, 105)),
            ],
            "13-06-2026 09:07:49 PM",
        ),
        # A camera name on the same row stays out of the clock's box.
        (
            [("08-08-2026 21:09:13", (0, 0, 460, 40)), ("GDM-Rambaugh_PTZ2", (1500, 0, 1910, 40))],
            "08-08-2026 21:09:13",
        ),
        # A weekday between date and time belongs to the clock.
        (
            [
                ("2026-08-03", (0, 0, 220, 40)),
                ("Mon", (240, 0, 300, 40)),
                ("21:00:43", (320, 0, 480, 40)),
            ],
            "2026-08-03 Mon 21:00:43",
        ),
        ([("Camera 01", (900, 0, 1100, 40))], None),
    ],
)
def test_the_clock_is_assembled_from_its_own_boxes(
    lines: list[tuple[str, tuple[int, int, int, int]]], expected: str | None
) -> None:
    found = _clock_lines(lines)
    assert (found[0] if found else None) == expected


def test_the_clock_in_the_bottom_band_is_found() -> None:
    """Some cameras print the clock bottom-left; the box is remembered in
    whole-frame fractions so the bottom band maps back correctly."""

    class BottomEngine(_FakeEngine):
        def find(self, image: np.ndarray) -> list[tuple[str, tuple[int, int, int, int]]]:
            self.finds += 1
            return self.lines if self.finds == 2 else []

    engine = BottomEngine([("14-06-2026 12:10:04 AM", (100, 20, 600, 70))], box_text=None)
    reader = FrameClockReader(engine=engine)
    assert reader.observe(_blank_frame(), pts_ms=1000.0) is not None
    assert reader._preferred is not None
    assert reader._preferred.region[0] > 0.85, "the box sits in the bottom band"
