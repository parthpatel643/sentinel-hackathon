"""Tests for catalogue camera-name formatting.

Every `raw` string below is a real name from the government catalogue. The
point of these tests is that a label has to *name something*: the failure
mode worth guarding against is a split that leaves "Circle" or "CCTV" as the
entire label, which is worse than the messy original.
"""

from __future__ import annotations

import pytest

from sentinel_core.camera_names import format_camera_name


@pytest.mark.parametrize(
    ("raw", "label", "locality"),
    [
        # A trailing place is a locality suffix and belongs on the second line.
        ("06 Timbavadi gate-Junagadh", "Timbavadi Gate", "Junagadh"),
        ("08 majewadi-gate-junagadh", "Majewadi Gate", "Junagadh"),
        ("11 dolatpara-junagadh", "Dolatpara", "Junagadh"),
        ("07 hero-showroom-gir-somnath", "Hero Showroom", "Gir Somnath"),
        # A trailing disambiguator may follow the place.
        ("09 new-bypass-near-by-circle-junagadh-2", "New Bypass Near By Circle 2", "Junagadh"),
        ("10 char-chowk-road-2-junagadh", "Char Chowk Road 2", "Junagadh"),
        # Administrative hierarchy is location, not identity.
        (
            "19 KHAPARIA GRAM PANCHAYAT , TALUKA GANDEVI, DISTRICT NAVSARI",
            "Khaparia Gram Panchayat",
            "Taluka Gandevi, District Navsari",
        ),
    ],
)
def test_a_trailing_place_becomes_the_locality(raw: str, label: str, locality: str) -> None:
    result = format_camera_name(raw)
    assert result.label == label
    assert result.locality == locality


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        # A place at the FRONT is part of the landmark's own name. Splitting
        # these leaves labels of "Circle", "CCTV" and "P2", which name nothing.
        ("04 Paldi Circle", "Paldi Circle"),
        ("18 Rajkot CCTV", "Rajkot CCTV"),
        ("17 Rajkot Bus Port CCTV", "Rajkot Bus Port CCTV"),
        ("16 Visat P2", "Visat P2"),
        ("23 Patan Dethali Char Rasta", "Patan Dethali Char Rasta"),
        ("Gandhidham Rambaugh p2", "Gandhidham Rambaugh P2"),
        # A place in the middle is not a suffix either.
        ("12 Tri Mandir Adalaj Tollnaka", "Tri Mandir Adalaj Tollnaka"),
    ],
)
def test_a_leading_place_stays_part_of_the_label(raw: str, label: str) -> None:
    result = format_camera_name(raw)
    assert result.label == label
    assert result.locality == ""


def test_a_name_that_is_only_a_place_keeps_it_as_the_label() -> None:
    """Splitting "bilimora" would leave an empty label."""
    for raw in ("33 dehgam", "36 bilimora"):
        result = format_camera_name(raw)
        assert result.label in {"Dehgam", "Bilimora"}
        assert result.locality == ""


def test_the_leading_index_is_dropped() -> None:
    """It duplicates the marker badge and the camera id."""
    assert format_camera_name("01 Chiman bhai Bridge").label == "Chiman bhai Bridge"


def test_honorific_particles_stay_lowercase_but_numerals_do_not() -> None:
    """"bhai" is an honorific; "teen"/"char" are Gujarati numerals naming a
    three- or four-way junction and must stay capitalised."""
    assert format_camera_name("01 Chiman bhai Bridge").label == "Chiman bhai Bridge"
    assert format_camera_name("05 Visat teen Rasta").label == "Visat Teen Rasta"


def test_known_acronyms_are_not_title_cased() -> None:
    assert format_camera_name("13 CN Vidhyalaya").label == "CN Vidhyalaya"
    assert "CCTV" in format_camera_name("18 Rajkot CCTV").label


def test_hand_entry_punctuation_is_cleaned() -> None:
    result = format_camera_name("42 Some  Place , Near   Thing")
    assert "  " not in result.label
    assert " ," not in result.label


def test_an_empty_name_falls_back_to_the_camera_id() -> None:
    """A marker must never be unlabelled."""
    assert format_camera_name("", camera_id="cam42").label == "cam42"
    assert format_camera_name("   ", camera_id="cam42").label == "cam42"
    assert format_camera_name("07", camera_id="cam42").label == "cam42"


def test_full_joins_label_and_locality_for_single_line_use() -> None:
    assert format_camera_name("08 majewadi-gate-junagadh").full == "Majewadi Gate · Junagadh"
    assert format_camera_name("04 Paldi Circle").full == "Paldi Circle"
