"""Plate normalisation decides whether a watchlist hit fires or is missed."""

from __future__ import annotations

import pytest

from sentinel_core.plates import (
    ambiguity_key,
    correct_plate_grammar,
    is_valid_plate,
    normalise_plate,
)


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


@pytest.mark.parametrize(
    ("read", "expected"),
    [
        ("GJQ3JC5583", "GJ03JC5583"),  # district digit read as a letter
        ("GJO3MH7800", "GJ03MH7800"),
        ("6J05RC9803", "GJ05RC9803"),  # state code letter read as a digit
        ("GJ01R55926", "GJ01RS5926"),  # series letter read as a digit
        ("GJ01HM795Z", "GJ01HM7952"),  # registration digit read as a letter
        ("GJ01HM7952", "GJ01HM7952"),  # already valid: untouched
    ],
)
def test_correct_plate_grammar_resolves_letter_digit_confusions(read: str, expected: str) -> None:
    assert correct_plate_grammar(read) == expected


@pytest.mark.parametrize(
    "read",
    [
        "GJ1MM75",  # too short for any layout: a missing character is never invented
        "GJ01HM79X2",  # X is not confusable with a digit
        "XX01AB1234",  # no real state code fits
    ],
)
def test_correct_plate_grammar_leaves_unfixable_reads_alone(read: str) -> None:
    assert correct_plate_grammar(read) == read


def test_correct_plate_grammar_prefers_the_layout_needing_fewest_swaps() -> None:
    # Nine characters fit GJ 1 AB 1234 and GJ 11 A 1234. Reading the 8 as a
    # B costs one swap; reading the B as an 8 then the 8 as a B costs two.
    assert correct_plate_grammar("GJ1B81234") == "GJ1BB1234"


@pytest.mark.parametrize("read", ["GJQ3JC5583", "6J05RC9803", "GJ01R55926", "GJ01HM795Z"])
def test_correction_never_changes_the_ambiguity_key(read: str) -> None:
    assert ambiguity_key(correct_plate_grammar(read)) == ambiguity_key(read)
