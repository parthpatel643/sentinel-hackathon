"""Tests for reading the camera's burned-in clock.

The parsing cases here are not invented: every malformed string below is
real Tesseract output observed against frames from the government grid. The
OSD font reads reliably digit-by-digit and drops separators unpredictably,
so tolerating that is the whole job.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from edge_agent.analytics.frame_clock import (
    _ATTEMPTS,
    IST,
    FrameClockReader,
    parse_overlay_timestamp,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Every malformed form here is real Tesseract output from grid frames.
        ("17-06-2026 18:04:42", (2026, 6, 17, 12, 34, 42)),
        ("17-06-202618:04:42", (2026, 6, 17, 12, 34, 42)),  # date/time run together
        ("13-06-2026 2102:28", (2026, 6, 13, 15, 32, 28)),  # a dropped colon
        ("  17-06-2026  18:04:42  ", (2026, 6, 17, 12, 34, 42)),
    ],
)
def test_separators_are_optional(text: str, expected: tuple[int, ...]) -> None:
    """Tesseract drops separators from this OSD font unpredictably; the
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


def _reader_reading(texts: dict[int, str | None], **kwargs: float) -> FrameClockReader:
    """A reader whose OCR returns `texts[second]` for a frame at that second
    of stream time — the frame's own overlay, as the camera printed it."""
    reader = FrameClockReader(**kwargs)  # type: ignore[arg-type]
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
    reader = FrameClockReader()
    assert reader.observe(_blank_frame(), pts_ms=1000.0) is None
    assert reader.verified(1000.0) is None


def test_the_overlay_is_read_at_most_once_per_stream_second() -> None:
    """The overlay changes once a second; OCR on every frame would be 25x
    the cost for the same answer."""
    reader = FrameClockReader()
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
    is still read, and confirmed by the reading earlier in that second."""
    reader = _reader_reading({1: "17-06-2026 18:04:42"})
    reader.observe(_blank_frame(), pts_ms=1000.0)
    assert reader.observe(_blank_frame(), pts_ms=1500.0) is None
    assert reader.read_now(_blank_frame(), pts_ms=1500.0) == _utc("17-06-2026 18:04:42")
    assert reader.verified(1500.0) == _utc("17-06-2026 18:04:42")


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
    """Each attempt on an unread camera shells out to tesseract for every
    region and variant. A camera whose overlay is unreadable would otherwise
    pay that every second forever, for no information."""
    reader = FrameClockReader(failure_backoff_after=3, failure_backoff_s=30.0)
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
    reader = FrameClockReader(failure_backoff_after=2)
    reader._preferred = _ATTEMPTS[0]
    attempts = 0

    def failing(frame: np.ndarray) -> str | None:
        nonlocal attempts
        attempts += 1
        return None

    reader._ocr = failing  # type: ignore[method-assign]
    for second in range(1, 8):
        reader.observe(_blank_frame(), pts_ms=second * 1000.0)
    assert attempts == 7


def test_the_working_region_is_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every attempt is a Tesseract call. A camera whose overlay needs the
    fifth attempt pays for five once, then for one."""
    import pytesseract

    calls: list[str] = []

    def image_to_string(image: np.ndarray, config: str) -> str:
        calls.append(config)
        return "17-06-2026 18:04:42" if "--psm 11" in config else ""

    monkeypatch.setattr(pytesseract, "image_to_string", image_to_string)
    reader = FrameClockReader(full_scan_interval_s=30.0)
    assert reader.observe(_blank_frame(), pts_ms=1000.0) is not None
    first_scan = len(calls)
    assert first_scan > 1

    calls.clear()
    reader.observe(_blank_frame(), pts_ms=2000.0)
    assert len(calls) == 1
    assert "--psm 11" in calls[0]


def test_eager_reads_more_often_while_a_vehicle_needs_evidence() -> None:
    """Any frame of a passing vehicle may become its evidence, so while one
    needs a clock frame the overlay is read more than once a second — up to
    a cap, because each read is a Tesseract process."""
    reader = FrameClockReader(max_reads_per_second=2)
    calls = 0

    def counting(frame: np.ndarray) -> str | None:
        nonlocal calls
        calls += 1
        return "17-06-2026 18:04:42"

    reader._ocr = counting  # type: ignore[method-assign]
    for pts in (1000.0, 1250.0, 1500.0, 1750.0):
        reader.observe(_blank_frame(), pts_ms=pts, eager=True)
    assert calls == 2, "capped at max_reads_per_second: each read is a Tesseract process"
    assert reader.verified(1250.0) is not None, "frames in one second confirm each other"


def test_the_attempt_that_reads_best_is_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    """Found on the grid: the first crop to read a camera misread its year as
    2036 on a third of frames while a looser crop read every one. Attempts
    are ranked by how often they have read this camera's clock."""
    import pytesseract

    calls: list[str] = []
    frame_number = {"n": 0}

    def image_to_string(image: np.ndarray, config: str) -> str:
        calls.append(config)
        # The first attempt reads only every other frame; sparse text reads all.
        if "--psm 11" in config:
            return "17-06-2026 18:04:42"
        return "17-06-2026 18:04:42" if frame_number["n"] % 2 == 0 else ""

    monkeypatch.setattr(pytesseract, "image_to_string", image_to_string)
    reader = FrameClockReader(full_scan_interval_s=0.0)
    for n in range(1, 6):
        frame_number["n"] = n
        reader.observe(_blank_frame(), pts_ms=n * 1000.0)
    assert reader._preferred is not None
    assert reader._preferred.psm == 11
