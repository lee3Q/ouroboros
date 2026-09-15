"""Tests for deterministic ambiguity evidence scoring."""

import json
from pathlib import Path

import pytest

from ouroboros.bigbang.ambiguity_evidence import (
    AmbiguityEvidenceEntry,
    AmbiguityEvidenceLedger,
    AmbiguityEvidenceSourceKind,
    AmbiguityEvidenceStatus,
    EvidenceConflict,
    EvidenceSource,
    parse_ambiguity_evidence_ledger,
)
from ouroboros.bigbang.ambiguity_formula import (
    AmbiguityFormulaResult,
    score_ambiguity_evidence,
)

_GOLDEN_PATH = Path(__file__).parents[2] / "fixtures/bigbang/ambiguity_formula_golden.json"
_GOLDEN_CASES = json.loads(_GOLDEN_PATH.read_text())["cases"]


def _source(quote: str = "The requirement is recorded.") -> EvidenceSource:
    return EvidenceSource(
        kind=AmbiguityEvidenceSourceKind.INTERVIEW_ANSWER,
        quote=quote,
    )


def _ledger(entries: list[dict[str, str]]) -> AmbiguityEvidenceLedger:
    evidence_entries = []
    for item in entries:
        status = AmbiguityEvidenceStatus(item["status"])
        source = None if status is AmbiguityEvidenceStatus.MISSING else _source()
        conflict = (
            EvidenceConflict(
                source=_source("A conflicting requirement is recorded."),
                explanation="The quoted requirements disagree.",
            )
            if status is AmbiguityEvidenceStatus.CONFLICTING
            else None
        )
        evidence_entries.append(
            AmbiguityEvidenceEntry(
                dimension=item["dimension"],
                field=item["field"],
                status=status,
                source=source,
                conflict=conflict,
            )
        )
    return AmbiguityEvidenceLedger(entries=tuple(evidence_entries))


def _expected_result(case: dict[str, object]) -> AmbiguityFormulaResult:
    expected = case["expected"]
    assert isinstance(expected, dict)
    overall_score = expected["overall_score"]
    dimension_scores = expected["dimension_scores"]
    assert isinstance(overall_score, float)
    assert isinstance(dimension_scores, list)
    return AmbiguityFormulaResult(
        overall_score=overall_score,
        dimension_scores=tuple((dimension, score) for dimension, score in dimension_scores),
    )


@pytest.mark.parametrize("case", _GOLDEN_CASES, ids=lambda case: case["name"])
def test_scores_match_complete_golden_fixture(case: dict[str, object]) -> None:
    entries = case["entries"]
    assert isinstance(entries, list)
    ledger = _ledger(entries)

    first = score_ambiguity_evidence(ledger)
    repeated = score_ambiguity_evidence(ledger)
    reordered = score_ambiguity_evidence(
        AmbiguityEvidenceLedger(entries=tuple(reversed(ledger.entries)))
    )

    assert first == _expected_result(case)
    assert repeated == first
    assert reordered == first


def test_rejects_unknown_dimensions() -> None:
    ledger = _ledger(
        [
            {
                "dimension": "unrecognized_dimension",
                "field": "primary",
                "status": "confirmed",
            }
        ]
    )

    with pytest.raises(ValueError, match="unrecognized_dimension"):
        score_ambiguity_evidence(ledger)


def test_bounded_evidence_requires_provenance() -> None:
    with pytest.raises(ValueError, match="bounded evidence requires a source quote"):
        AmbiguityEvidenceEntry(
            dimension="goal",
            field="outcome",
            status=AmbiguityEvidenceStatus.BOUNDED,
        )


def test_parser_rejects_model_supplied_numeric_fields() -> None:
    payload = {
        "entries": [
            {
                "dimension": "goal",
                "field": "outcome",
                "status": "bounded",
                "source": {
                    "kind": "interview_answer",
                    "quote": "Generate a release report.",
                },
            }
        ],
        "field_weight": 1.0,
    }

    with pytest.raises(ValueError, match="field_weight"):
        parse_ambiguity_evidence_ledger(json.dumps(payload))


def test_bounded_ledger_serialization_is_stable() -> None:
    goal = AmbiguityEvidenceEntry(
        dimension="goal",
        field="outcome",
        status=AmbiguityEvidenceStatus.BOUNDED,
        source=_source(),
    )
    constraints = AmbiguityEvidenceEntry(
        dimension="constraints",
        field="network_access",
        status=AmbiguityEvidenceStatus.CONFIRMED,
        source=_source(),
    )

    first = AmbiguityEvidenceLedger(entries=(goal, constraints))
    second = AmbiguityEvidenceLedger(entries=(constraints, goal))

    assert first.canonical_json() == second.canonical_json()
    assert '"status":"bounded"' in first.canonical_json()
