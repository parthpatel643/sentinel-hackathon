"""Plate normalisation decides whether a watchlist hit fires or is missed."""

from __future__ import annotations

import pytest

from sentinel_core.plates import ambiguity_key, is_valid_plate, normalise_plate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("gj 01 ab 1234", "GJ01AB1234"),
        ("GJ-01-AB-1234", "GJ01AB1234"),
        ("INDGJ01AB1234", "GJ01AB1234"),
        ("  gj01ab1234  ", "GJ01AB1234"),
        ("IND", "IND"),
    ],
)
def test_normalise_plate(raw: str, expected: str) -> None:
    assert normalise_plate(raw) == expected


@pytest.mark.parametrize(
    "plate",
    ["GJ01AB1234", "GJ1A1234", "MH12DE1433", "GJ18ABC1234", "22BH6517A", "22BH6517AB"],
)
def test_valid_plates(plate: str) -> None:
    assert is_valid_plate(plate)


@pytest.mark.parametrize(
    "plate",
    [
        "XX01AB1234",  # XX is not a real RTO state code — almost always a misread
        "GJ01AB123",  # too few digits
        "GJ01AB12345",  # too many digits
        "G101AB1234",  # digit in the state-code position
        "",
    ],
)
def test_invalid_plates(plate: str) -> None:
    assert not is_valid_plate(plate)


def test_state_code_check_can_be_relaxed() -> None:
    assert is_valid_plate("XX01AB1234", check_state_code=False)


def test_ambiguity_key_collapses_ocr_confusions() -> None:
    """The whole point: a misread still collides with the truth on one lookup."""
    truth = ambiguity_key("GJ01AB1234")

    assert ambiguity_key("GJO1AB1Z34") == truth
    assert ambiguity_key("6JO1A81Z34") == truth
    assert ambiguity_key("GJ 01 AB 1234") == truth


def test_ambiguity_key_does_not_collapse_distinct_plates() -> None:
    assert ambiguity_key("GJ01AB1234") != ambiguity_key("GJ01AB1235")
    assert ambiguity_key("GJ01AB1234") != ambiguity_key("MH01AB1234")
