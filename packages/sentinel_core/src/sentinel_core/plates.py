"""Indian number-plate normalisation, validation and OCR-ambiguity folding.

This module is the reason a mediocre OCR read can still find the right vehicle.
It is deliberately dependency-free and exhaustively tested: every rung of the
watchlist matching ladder is built on top of it.
"""

from __future__ import annotations

import re

__all__ = [
    "AMBIGUITY_CLASSES",
    "RTO_STATE_CODES",
    "ambiguity_key",
    "is_valid_plate",
    "normalise_plate",
]

# Standard format: GJ 01 AB 1234 -> two-letter RTO state code, 1-2 digit district,
# 1-3 letter series, 4-digit number.
_STANDARD = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")
# Bharat series: 22 BH 6517 A
_BH_SERIES = re.compile(r"^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$")

_NON_ALNUM = re.compile(r"[^A-Z0-9]")
# HSRP plates carry an "IND" country mark next to the hologram; OCR often reads it.
_IND_PREFIX = re.compile(r"^IND")

RTO_STATE_CODES: frozenset[str] = frozenset(
    {
        "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ",
        "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
        "MZ", "NL", "OD", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK", "UP",
        "WB",
    }
)  # fmt: skip

# Characters an OCR confuses under motion blur, low light and oblique angles.
# Folding them to one representative lets a misread collide with the truth on a
# single index lookup instead of needing a fuzzy scan.
AMBIGUITY_CLASSES: dict[str, str] = {
    "O": "0", "D": "0", "Q": "0",
    "I": "1", "L": "1",
    "Z": "2",
    "S": "5",
    "B": "8",
    "G": "6",
    "A": "4",
}  # fmt: skip


def normalise_plate(raw: str) -> str:
    """Canonical form used for exact matching and storage.

    Uppercases, strips separators and the HSRP `IND` country mark.
    """
    cleaned = _NON_ALNUM.sub("", raw.upper())
    stripped = _IND_PREFIX.sub("", cleaned)
    # Only strip IND when something plausible remains; "IND" alone is a bad read.
    return stripped if len(stripped) >= 4 else cleaned


def is_valid_plate(plate: str, *, check_state_code: bool = True) -> bool:
    """True when the plate matches Indian plate grammar.

    A two-letter prefix that is not a real RTO code is almost always a misread,
    so validating it is free accuracy.
    """
    normalised = normalise_plate(plate)
    if _BH_SERIES.match(normalised):
        return True
    if not _STANDARD.match(normalised):
        return False
    return not (check_state_code and normalised[:2] not in RTO_STATE_CODES)


def ambiguity_key(plate: str) -> str:
    """Fold OCR-confusable characters to a canonical class.

    `GJO1AB1Z34` and `GJ01AB1234` produce the same key, so a watchlist lookup
    finds the vehicle despite the misread.
    """
    normalised = normalise_plate(plate)
    return "".join(AMBIGUITY_CLASSES.get(ch, ch) for ch in normalised)
