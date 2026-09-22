"""Temporal voting is the single biggest accuracy lever in the ANPR chain —
these tests are the evidence that it actually beats a single-frame read."""

from __future__ import annotations

from edge_agent.analytics.plate_reader import PlateCandidate
from edge_agent.analytics.voting import PlateVoter


def _candidate(text: str, confidences: tuple[float, ...] | None = None) -> PlateCandidate:
    return PlateCandidate(
        text=text,
        char_confidences=confidences or tuple(0.9 for _ in text),
        bbox_xyxy=(0.0, 0.0, 10.0, 10.0),
    )


def test_no_reads_yields_no_resolution() -> None:
    assert PlateVoter().resolve() is None


def test_a_single_read_is_returned_as_is() -> None:
    voter = PlateVoter()
    voter.add(_candidate("GJ01AB1234"))

    resolved = voter.resolve()

    assert resolved is not None
    assert resolved.plate_text == "GJ01AB1234"
    assert resolved.frames_voted == 1


def test_majority_vote_corrects_a_single_frame_misread() -> None:
    """The whole point: one bad frame among many good ones must not corrupt
    the resolved plate."""
    voter = PlateVoter()
    voter.add(_candidate("GJ01AB1234"))
    voter.add(_candidate("GJ01AB1234"))
    voter.add(_candidate("GJ01AB1234"))
    voter.add(_candidate("GJ018B1234"))  # one bad frame: 0<->8 at position 4

    resolved = voter.resolve()

    assert resolved is not None
    assert resolved.plate_text == "GJ01AB1234"
    assert resolved.frames_voted == 4


def test_confidence_weighting_lets_a_high_confidence_minority_win() -> None:
    """A single very confident read can outweigh several low-confidence
    reads at one position — this is why voting is weighted, not a plain
    majority count."""
    voter = PlateVoter()
    # Three low-confidence reads say 'B' at the last position...
    for _ in range(3):
        voter.add(_candidate("GJ01AB123B", confidences=(0.9,) * 9 + (0.2,)))
    # ...but one highly confident read says '4'.
    voter.add(_candidate("GJ01AB1234", confidences=(0.9,) * 9 + (0.99,)))

    resolved = voter.resolve()

    assert resolved is not None
    assert resolved.plate_text[-1] == "4"


def test_reads_of_a_different_length_are_voted_separately() -> None:
    """A partially occluded plate producing a shorter read must not corrupt
    the position-by-position vote for the length most reads agree on."""
    voter = PlateVoter()
    voter.add(_candidate("GJ01AB1234"))
    voter.add(_candidate("GJ01AB1234"))
    voter.add(_candidate("J01AB1234"))  # one character short (occlusion)

    resolved = voter.resolve()

    assert resolved is not None
    assert resolved.plate_text == "GJ01AB1234"
    assert resolved.frames_voted == 2  # only the modal-length reads counted


def test_disagreement_is_flagged_uncertain_not_silently_guessed() -> None:
    """A close call must be visible to the operator (03-UX-DESIGN.md section
    2.2), not hidden behind a confident-looking resolved string."""
    voter = PlateVoter(uncertain_threshold=0.6)
    voter.add(_candidate("GJ01AB1234", confidences=(0.9,) * 9 + (0.9,)))
    voter.add(_candidate("GJ01AB1235", confidences=(0.9,) * 9 + (0.9,)))  # 50/50 split at last char

    resolved = voter.resolve()

    assert resolved is not None
    assert 9 in resolved.uncertain_positions


def test_format_valid_reflects_indian_plate_grammar() -> None:
    voter = PlateVoter()
    voter.add(_candidate("GJ01AB1234"))
    assert voter.resolve().format_valid is True  # type: ignore[union-attr]

    invalid_voter = PlateVoter()
    invalid_voter.add(_candidate("XX01AB1234"))  # not a real RTO state code
    assert invalid_voter.resolve().format_valid is False  # type: ignore[union-attr]


def test_ambiguity_key_is_populated_for_watchlist_matching() -> None:
    voter = PlateVoter()
    voter.add(_candidate("GJ01AB1234"))

    resolved = voter.resolve()

    assert resolved is not None
    assert resolved.plate_ambiguity_key  # non-empty; exact folding tested in sentinel_core


def test_empty_candidate_text_is_never_added() -> None:
    """A detector-only, OCR-failed read must not pollute the vote."""
    voter = PlateVoter()
    voter.add(_candidate(""))

    assert voter.reads_seen == 0
    assert voter.resolve() is None


def test_resolve_can_be_called_every_frame_and_refines_over_time() -> None:
    """Frigate's own description of its LPR: 'continuously refines the
    recognition process, keeping the most confident result.' Calling
    resolve() mid-track must be safe and must reflect only what has been
    seen so far."""
    voter = PlateVoter()

    voter.add(_candidate("GJ01AB123X", confidences=(0.9,) * 9 + (0.3,)))
    early = voter.resolve()
    assert early is not None
    assert early.plate_text[-1] == "X"

    voter.add(_candidate("GJ01AB1234", confidences=(0.9,) * 9 + (0.95,)))
    voter.add(_candidate("GJ01AB1234", confidences=(0.9,) * 9 + (0.95,)))
    later = voter.resolve()
    assert later is not None
    assert later.plate_text[-1] == "4"
    assert later.frames_voted == 3
