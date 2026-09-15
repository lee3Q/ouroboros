"""Code-owned deterministic scoring for ambiguity evidence."""

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from ouroboros.bigbang.ambiguity_evidence import (
    AmbiguityEvidenceEntry,
    AmbiguityEvidenceLedger,
    AmbiguityEvidenceStatus,
)

CANONICAL_DIMENSIONS: Final[tuple[str, ...]] = (
    "goal",
    "actors_context",
    "scope_non_goals",
    "constraints",
    "success_criteria",
    "inputs_outputs",
    "ownership_decision_authority",
    "verification",
)
"""The complete, ordered set of dimensions for baseline scoring."""

_CRITICAL_DIMENSIONS: Final = CANONICAL_DIMENSIONS
_FIELD_WEIGHT: Final = Fraction(1)
_DIMENSION_WEIGHT: Final = Fraction(1)
_CRITICAL_MULTIPLIER: Final = Fraction(4, 5)
_CONFLICT_FLOOR: Final = Fraction(1)
_OMITTED_DIMENSION_SCORE: Final = Fraction(1)
_STATUS_UNCERTAINTIES: Final[Mapping[AmbiguityEvidenceStatus, Fraction]] = MappingProxyType(
    {
        AmbiguityEvidenceStatus.CONFIRMED: Fraction(0),
        AmbiguityEvidenceStatus.BOUNDED: Fraction(1, 4),
        AmbiguityEvidenceStatus.INFERRED: Fraction(3, 5),
        AmbiguityEvidenceStatus.MISSING: Fraction(1),
        AmbiguityEvidenceStatus.CONFLICTING: Fraction(1),
    }
)


@dataclass(frozen=True, slots=True)
class AmbiguityFormulaResult:
    """Immutable ambiguity scores in ``CANONICAL_DIMENSIONS`` order."""

    overall_score: float
    dimension_scores: tuple[tuple[str, float], ...]


def _score_dimension(entries: tuple[AmbiguityEvidenceEntry, ...]) -> Fraction:
    if not entries:
        return _OMITTED_DIMENSION_SCORE
    total = sum(
        (_STATUS_UNCERTAINTIES[entry.status] * _FIELD_WEIGHT for entry in entries), Fraction()
    )
    return total / (len(entries) * _FIELD_WEIGHT)


def score_ambiguity_evidence(ledger: AmbiguityEvidenceLedger) -> AmbiguityFormulaResult:
    """Calculate repository-owned ambiguity scores from a typed evidence ledger.

    Unknown dimensions fail closed. Every canonical dimension is critical, and
    absent dimensions receive the maximum ambiguity score.
    """
    unknown_dimensions = tuple(
        entry.dimension for entry in ledger.entries if entry.dimension not in CANONICAL_DIMENSIONS
    )
    if unknown_dimensions:
        raise ValueError(
            f"ambiguity evidence contains unknown dimensions: {', '.join(unknown_dimensions)}"
        )

    dimension_scores = tuple(
        (
            dimension,
            _score_dimension(
                tuple(entry for entry in ledger.entries if entry.dimension == dimension)
            ),
        )
        for dimension in CANONICAL_DIMENSIONS
    )
    weighted_mean = sum(
        (score * _DIMENSION_WEIGHT for _, score in dimension_scores), Fraction()
    ) / (len(dimension_scores) * _DIMENSION_WEIGHT)
    highest_critical_score = max(
        score for dimension, score in dimension_scores if dimension in _CRITICAL_DIMENSIONS
    )
    conflict_floor = (
        _CONFLICT_FLOOR
        if any(entry.status is AmbiguityEvidenceStatus.CONFLICTING for entry in ledger.entries)
        else Fraction()
    )
    overall_score = max(
        weighted_mean,
        _CRITICAL_MULTIPLIER * highest_critical_score,
        conflict_floor,
    )

    return AmbiguityFormulaResult(
        overall_score=float(overall_score),
        dimension_scores=tuple((dimension, float(score)) for dimension, score in dimension_scores),
    )
