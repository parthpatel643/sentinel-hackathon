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

from edge_agent.analytics.frame_clock import IST, FrameClockReader, parse_overlay_timestamp


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


def test_a_frame_with_no_readable_clock_yields_none() -> None:
    """A black frame has no overlay. The caller keeps its PTS-derived time."""
    assert FrameClockReader().read(_blank_frame()) is None


def test_a_reading_is_cached_within_the_same_stream_second() -> None:
    """The overlay changes once a second; OCR on every frame would be 25x
    the cost for the same answer."""
    reader = FrameClockReader()
    calls = 0

    def counting(frame: np.ndarray) -> str | None:
        nonlocal calls
        calls += 1
        return "17-06-2026 18:04:42"

    reader._ocr = counting  # type: ignore[method-assign]
    # Two distinct seconds to establish a corroborated anchor.
    reader.read(_blank_frame(), pts_ms=1000.0)
    established = reader.read(_blank_frame(), pts_ms=2000.0)
    assert established == datetime(2026, 6, 17, 12, 34, 42, tzinfo=UTC)
    assert calls == 2

    same_second = reader.read(_blank_frame(), pts_ms=2400.0)
    assert same_second == established
    assert calls == 2, "OCR must not re-run within the same second of stream time"

    reader.read(_blank_frame(), pts_ms=3100.0)
    assert calls == 3, "a new second should re-read the overlay"


def test_a_single_disagreeing_reading_does_not_move_the_clock() -> None:
    """A single inserted digit turns 21:02 into 21:10 — it parses perfectly
    and is wrong, so one reading is never enough to overturn a trusted one."""
    reader = FrameClockReader(max_jump_s=600.0)
    reader._ocr = lambda frame: "17-06-2026 18:04:42"  # type: ignore[method-assign]
    reader.read(_blank_frame(), pts_ms=1000.0)
    established = reader.read(_blank_frame(), pts_ms=2000.0)
    assert established is not None

    reader._ocr = lambda frame: "17-06-2026 23:59:59"  # type: ignore[method-assign]
    assert reader.read(_blank_frame(), pts_ms=3000.0) == established


def test_two_agreeing_readings_heal_a_wrong_anchor() -> None:
    """Found in production: once the clock locked onto a misread, every
    CORRECT reading afterwards was rejected as a jump and the timestamp
    froze on the wrong value. A corroborated reading has to be able to
    overturn the anchor, or a single bad frame poisons the camera forever.
    """
    reader = FrameClockReader(max_jump_s=600.0)
    reader._ocr = lambda frame: "17-06-2026 02:00:00"  # type: ignore[method-assign]
    reader.read(_blank_frame(), pts_ms=1000.0)
    reader.read(_blank_frame(), pts_ms=2000.0)

    # The real time, far enough away to be rejected as a one-off.
    reader._ocr = lambda frame: "17-06-2026 18:04:42"  # type: ignore[method-assign]
    reader.read(_blank_frame(), pts_ms=3000.0)  # candidate only
    healed = reader.read(_blank_frame(), pts_ms=4000.0)  # corroborated
    assert healed == datetime(2026, 6, 17, 12, 34, 42, tzinfo=UTC)


def test_a_future_timestamp_is_refused() -> None:
    """Found in production: a year misread as 2036 instead of 2026 parses
    perfectly and passed a naive range check. Footage cannot be captured
    after it was processed, which is what makes this catchable at all."""
    reader = FrameClockReader()
    future = datetime.now(UTC).astimezone(IST) + timedelta(days=3650)
    reader._ocr = lambda frame: future.strftime("%d-%m-%Y %H:%M:%S")  # type: ignore[method-assign]
    assert reader.read(_blank_frame(), pts_ms=1000.0) is None
    assert reader.read(_blank_frame(), pts_ms=2000.0) is None, "not even when repeated"


def test_an_absurdly_old_timestamp_is_refused() -> None:
    reader = FrameClockReader(max_age_years=5)
    reader._ocr = lambda frame: "17-06-1999 18:04:42"  # type: ignore[method-assign]
    assert reader.read(_blank_frame(), pts_ms=1000.0) is None


def test_a_plausible_advance_is_accepted() -> None:
    reader = FrameClockReader(max_jump_s=600.0)
    reader._ocr = lambda frame: "17-06-2026 18:04:42"  # type: ignore[method-assign]
    reader.read(_blank_frame(), pts_ms=1000.0)
    reader.read(_blank_frame(), pts_ms=2000.0)

    reader._ocr = lambda frame: "17-06-2026 18:04:45"  # type: ignore[method-assign]
    advanced = reader.read(_blank_frame(), pts_ms=3000.0)
    assert advanced == datetime(2026, 6, 17, 12, 34, 45, tzinfo=UTC)


def test_a_camera_that_cannot_be_read_backs_off() -> None:
    """Each attempt shells out to tesseract for every crop and variant. A
    camera whose overlay is unreadable — one in the fleet sits over a lit
    shop front and never resolves — would otherwise pay that cost every
    second forever, for no information."""
    reader = FrameClockReader(failure_backoff_after=3, failure_backoff_s=30.0)
    attempts = 0

    def failing(frame: np.ndarray) -> str | None:
        nonlocal attempts
        attempts += 1
        return None

    reader._ocr = failing  # type: ignore[method-assign]
    for second in range(1, 11):
        reader.read(_blank_frame(), pts_ms=second * 1000.0)

    assert attempts == 3, "should stop attempting once the failure threshold is hit"

    # Well past the backoff window, it tries again rather than giving up forever.
    reader.read(_blank_frame(), pts_ms=45_000.0)
    assert attempts == 4


def test_a_successful_read_clears_the_backoff() -> None:
    reader = FrameClockReader(failure_backoff_after=2, failure_backoff_s=30.0)
    reader._ocr = lambda frame: None  # type: ignore[method-assign]
    reader.read(_blank_frame(), pts_ms=1000.0)
    reader.read(_blank_frame(), pts_ms=2000.0)

    reader._ocr = lambda frame: "17-06-2026 18:04:42"  # type: ignore[method-assign]
    reader.read(_blank_frame(), pts_ms=40_000.0)
    reader.read(_blank_frame(), pts_ms=41_000.0)
    assert reader.read(_blank_frame(), pts_ms=42_000.0) is not None
