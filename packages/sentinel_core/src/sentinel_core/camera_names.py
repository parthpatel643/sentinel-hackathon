"""Turning catalogue camera names into something readable on a map.

The government catalogue's names are operator shorthand, entered by many
hands over time, and they arrive in every shape at once::

    01 Chiman bhai Bridge
    07 hero-showroom-gir-somnath
    19 KHAPARIA GRAM PANCHAYAT , TALUKA GANDEVI, DISTRICT NAVSARI
    09 new-bypass-near-by-circle-junagadh-2
    37 bilimora

Rendered as-is on a map those are unreadable: a leading index that repeats
the marker badge, hyphens standing in for spaces, shouted administrative
hierarchy, and three cameras all called "bilimora".

This module derives a *display* name and a locality from that string. It
never replaces the catalogue's own `name`, which stays exactly as received —
an evidence trail has to be able to show the value the source system gave
us, not a prettied-up version of it.

It lives here, beside `_GUJARAT_PLACE_COORDS` in `gov_catalogue`, because
the locality split needs the same vocabulary of Gujarat places that the
geocoder already carries. Deriving it server-side also means the Movement
Report, the evidence CSV and the console all show a camera the same way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["CameraDisplayName", "format_camera_name"]

# Tokens that are shouted or abbreviated in the source and should stay that
# way rather than being title-cased into "Cctv" or "Ongc".
_ACRONYMS = frozenset(
    {
        "cctv",
        "ongc",
        "cn",
        "rto",
        "nh",
        "sh",
        "pwd",
        "gp",
        "ps",
        "atm",
        "id",
    }
)

# Honorific particles that stay lowercase mid-name, the way English writes
# "van" or "de". Deliberately short: "teen" and "char" are Gujarati numerals
# in junction names ("Teen Rasta", "Char Rasta") and must stay capitalised.
_PARTICLES = frozenset({"bhai", "ben"})

# Administrative qualifiers. Everything from the first one onwards describes
# *where* the camera is rather than *what* it watches, so it belongs on a
# second line, not in the label.
_ADMIN_MARKERS = ("taluka", "district", "dist.", "dist", "tal.", "tal")

# Known Gujarat places. Mirrors gov_catalogue._GUJARAT_PLACE_COORDS; longest
# first so "gir somnath" wins over a bare "somnath".
_PLACES: tuple[str, ...] = (
    "gir somnath",
    "gir-somnath",
    "chiman bhai bridge",
    "cn vidhyalaya",
    "gandhidham",
    "junagadh",
    "bilimora",
    "navsari",
    "gandevi",
    "dehgam",
    "adalaj",
    "rajkot",
    "patan",
    "paldi",
    "visat",
)


@dataclass(frozen=True)
class CameraDisplayName:
    """`label` is what goes on the marker; `locality` is the smaller second
    line, empty when the name carries no place information."""

    label: str
    locality: str

    @property
    def full(self) -> str:
        return f"{self.label} · {self.locality}" if self.locality else self.label


def _titlecase(text: str) -> str:
    words = []
    for index, word in enumerate(text.split()):
        lowered = word.lower()
        if lowered in _ACRONYMS:
            words.append(lowered.upper())
        elif lowered in _PARTICLES and index > 0:
            words.append(lowered)
        elif re.fullmatch(r"[a-z]?\d+", lowered):
            # Disambiguators like "p2" or a bare "2" — uppercase the letter,
            # keep the digit.
            words.append(lowered.upper())
        else:
            words.append(word[:1].upper() + word[1:].lower() if word else word)
    return " ".join(words)


def format_camera_name(raw: str, *, camera_id: str | None = None) -> CameraDisplayName:
    """Derive a readable label and locality from a catalogue name.

    Falls back to the camera id when a name reduces to nothing, so a marker
    is never unlabelled.
    """
    text = (raw or "").strip()
    if not text:
        return CameraDisplayName(label=camera_id or "Unnamed camera", locality="")

    # The leading index duplicates the marker's own badge and the camera id.
    text = re.sub(r"^\d{1,3}[\s._-]+", "", text)
    # A name that is *only* an index carries no information at all.
    if re.fullmatch(r"\d{1,3}", text.strip()):
        return CameraDisplayName(label=camera_id or "Unnamed camera", locality="")
    # Hyphens and underscores stand in for spaces in the machine-entered names.
    text = re.sub(r"[_-]+", " ", text)
    # " , " and doubled spaces come from hand entry.
    text = re.sub(r"\s+([,;])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;")

    if not text:
        return CameraDisplayName(label=camera_id or "Unnamed camera", locality="")

    lowered = text.lower()

    # Split off an administrative tail: "... , TALUKA GANDEVI, DISTRICT NAVSARI".
    admin_at = min(
        (m.start() for marker in _ADMIN_MARKERS if (m := re.search(rf"\b{marker}\b", lowered))),
        default=-1,
    )
    locality = ""
    if admin_at > 0:
        locality = _titlecase(text[admin_at:].strip(" ,;"))
        text = text[:admin_at].strip(" ,;")

    # Otherwise lift a recognised place, but only from the *end* of the name.
    # A place at the front is part of the landmark's own name — "Paldi Circle",
    # "Rajkot CCTV", "Visat P2" — and splitting those leaves a label of
    # "Circle" or "CCTV", which names nothing. A trailing place is a locality
    # suffix ("majewadi-gate-junagadh") and is exactly what belongs on line two.
    # A short disambiguator may follow it ("...-junagadh-2").
    if not locality:
        for place in _PLACES:
            match = re.search(
                rf"[\s,;]+{re.escape(place)}\b\s*([a-z]?\d{{1,2}})?\s*$",
                text,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            remainder = text[: match.start()].strip(" ,;")
            suffix = (match.group(1) or "").strip()
            if not remainder:
                break  # the whole name is the place — keep it as the label
            locality = _titlecase(place)
            text = f"{remainder} {suffix}".strip() if suffix else remainder
            break

    label = _titlecase(text.strip(" ,;")) or _titlecase(locality) or (camera_id or "Camera")
    if label == locality:
        locality = ""
    return CameraDisplayName(label=label, locality=locality)
