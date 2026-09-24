"""Temporal voting across a vehicle's track.

A vehicle is in frame for 1-3 seconds; at even a modest analytic rate that is
5-15 independent OCR reads of the same plate. Per-character, confidence-
weighted voting across those reads beats any single-frame read, including
much larger models — this is the single biggest accuracy lever in the whole
ANPR chain (see docs/02-ANPR-PIPELINE.md section 1).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from edge_agent.analytics.plate_reader import PlateCandidate
from sentinel_core.plates import ambiguity_key, is_valid_plate, normalise_plate

__all__ = ["PlateVoter", "VotedPlate"]


@dataclass(frozen=True, slots=True)
class VotedPlate:
    """Directly maps onto sentinel_core.schemas.AnprPayload's fields."""

    plate_text: str
    plate_normalised: str
    plate_ambiguity_key: str
    plate_confidence: float
    char_confidences: tuple[float, ...]
    format_valid: bool
    frames_voted: int
    uncertain_positions: tuple[int, ...]
    """0-indexed positions where the winning character did not clearly
    dominate — surfaced in the UI at reduced opacity (03-UX-DESIGN.md
    section 2.2) rather than silently guessed."""


@dataclass(slots=True)
class PlateVoter:
    """Accumulates PlateCandidate reads for one vehicle track and resolves
    them into a single best-estimate plate, refinable every frame."""

    uncertain_threshold: float = 0.6
    """A position is flagged uncertain when its winning character holds less
    than this share of the weighted vote — not a guess, a disagreement."""
    _candidates: list[PlateCandidate] = field(default_factory=list)

    def add(self, candidate: PlateCandidate) -> None:
        if candidate.text:
            self._candidates.append(candidate)

    @property
    def reads_seen(self) -> int:
        return len(self._candidates)

    def resolve(self) -> VotedPlate | None:
        """The current best estimate, or None if nothing has been read yet.

        Safe to call every frame — it recomputes from all reads seen so far,
        matching the "continuously refines" behaviour described for Frigate's
        LPR in docs/02-ANPR-PIPELINE.md section 1.
        """
        if not self._candidates:
            return None

        # Reads at one length are voted together; a plate misread as one
        # character short or long by a bad frame should not corrupt the
        # position-by-position vote for the length the reads agree on.
        #
        # Which length, though, cannot be decided by popularity alone. A
        # distant plate yields a stream of truncated reads that agree with
        # each other and with nothing real — measured on a live wide-area
        # camera, 8-character reads were 1% grammatically valid while
        # 9-character reads from the same footage were 60% valid, simply
        # because Indian plates are nine or ten characters. Taking the modal
        # length there discards the reads most likely to be right and votes
        # among the ones most likely to be wrong.
        #
        # So the plate grammar breaks the tie: if any read forms a valid
        # registration, only those lengths are considered. It is a prior
        # about what plates can be, not a guess about this one.
        valid_candidates = [c for c in self._candidates if is_valid_plate(normalise_plate(c.text))]
        pool = valid_candidates or self._candidates
        lengths = Counter(len(c.text) for c in pool)
        mode_length = lengths.most_common(1)[0][0]
        matching = [c for c in self._candidates if len(c.text) == mode_length]

        # Plain dicts, not collections.Counter: Counter's values are typed as
        # int (it counts occurrences), but these are confidence-weighted
        # sums of floats.
        position_votes: list[dict[str, float]] = [{} for _ in range(mode_length)]
        for candidate in matching:
            for i, char in enumerate(candidate.text):
                weight = (
                    candidate.char_confidences[i] if i < len(candidate.char_confidences) else 1.0
                )
                position_votes[i][char] = position_votes[i].get(char, 0.0) + weight

        resolved_chars: list[str] = []
        char_confidences: list[float] = []
        uncertain_positions: list[int] = []
        for i, votes in enumerate(position_votes):
            total_weight = sum(votes.values())
            winner, winner_weight = max(votes.items(), key=lambda item: item[1])
            share = winner_weight / total_weight if total_weight > 0 else 0.0
            resolved_chars.append(winner)
            char_confidences.append(share)
            if share < self.uncertain_threshold:
                uncertain_positions.append(i)

        plate_text = "".join(resolved_chars)
        mean_confidence = sum(char_confidences) / len(char_confidences) if char_confidences else 0.0

        return VotedPlate(
            plate_text=plate_text,
            plate_normalised=normalise_plate(plate_text),
            plate_ambiguity_key=ambiguity_key(plate_text),
            plate_confidence=mean_confidence,
            char_confidences=tuple(char_confidences),
            format_valid=is_valid_plate(plate_text),
            frames_voted=len(matching),
            uncertain_positions=tuple(uncertain_positions),
        )
