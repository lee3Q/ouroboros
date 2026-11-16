"""Unscored Seeds remain unscored through summaries, Auto gates and evolution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from ouroboros.auto.grading import GradeGate
from ouroboros.auto.ledger import SeedDraftLedger
from ouroboros.auto.pipeline import AutoPipeline
from ouroboros.auto.state import AutoPipelineState, AutoStore
from ouroboros.bigbang.interview import InterviewState
from ouroboros.bigbang.seed_generator import SeedGenerator
from ouroboros.core.seed import OntologySchema, Seed, SeedMetadata, ac_texts
from ouroboros.core.types import Result
from ouroboros.evolution.reflect import ReflectOutput
from ouroboros.mcp.tools.authoring_handlers import GenerateSeedHandler
from ouroboros.mcp.tools.session_seed_handler import handle_session_context_seed


def _seed(score: float | None, mode: str = "normal", *, degraded: bool = False) -> Seed:
    return Seed(
        goal="Build a local CLI",
        constraints=("No network access",),
        acceptance_criteria=("The command prints a task list to stdout",),
        ontology_schema=OntologySchema(name="TaskList", description="Local tasks"),
        metadata=SeedMetadata(ambiguity_score=score, generation_mode=mode, degraded=degraded),
    )


@pytest.mark.parametrize("mode", ["normal", "reviewed_console_preview"])
def test_numeric_gate_rejects_unmeasured_score_without_trusting_source_label(mode):
    seed = _seed(None, mode)
    result = GradeGate().grade_seed(seed)

    assert not result.may_run
    assert "missing_ambiguity_score" in {item.code for item in result.blockers}
    assert "high_ambiguity_score" not in {item.code for item in result.blockers}
    assert seed.metadata.ambiguity_score is None


@pytest.mark.parametrize("score, blocked", [(0.0, False), (0.2, False), (0.21, True)])
def test_measured_numeric_gate_keeps_legacy_threshold(score, blocked):
    result = GradeGate().grade_seed(_seed(score))

    assert ("high_ambiguity_score" in {item.code for item in result.blockers}) is blocked
    assert "missing_ambiguity_score" not in {item.code for item in result.blockers}


@pytest.mark.parametrize(
    "closure_mode, degraded", [("ledger_only", False), ("safe_default", False), (None, True)]
)
def test_existing_structural_gate_exceptions_keep_their_semantics(closure_mode, degraded):
    results = [
        GradeGate().grade_seed(
            _seed(score, "deadline_recovery" if degraded else "normal", degraded=degraded),
            closure_mode=closure_mode,
        )
        for score in (None, 0.1)
    ]

    assert [item.code for item in results[0].blockers] == [
        item.code for item in results[1].blockers
    ]


@pytest.mark.parametrize("score, expected", [(None, None), (0.12, 0.7), (0.9, 0.9)])
def test_pipeline_floor_preserves_absent_measurement_and_persisted_null(
    score, expected, tmp_path, monkeypatch
):
    monkeypatch.setattr("ouroboros.auto.pipeline.deterministic_floor", lambda _ledger: 0.7)
    pipeline = AutoPipeline(
        interview_driver=MagicMock(), seed_generator=AsyncMock(), store=AutoStore(tmp_path)
    )
    seed = _seed(score, "reviewed_console_preview" if score is None else "normal")
    state = AutoPipelineState(goal=seed.goal, cwd=str(tmp_path))

    recorded = pipeline._record_generated_seed(state, SeedDraftLedger.from_goal(seed.goal), seed)

    assert recorded.metadata.ambiguity_score == expected
    assert state.seed_artifact["metadata"]["ambiguity_score"] == expected
    reloaded = Seed.from_dict(yaml.safe_load(yaml.safe_dump(state.seed_artifact)))
    assert reloaded.metadata.ambiguity_score == expected


@pytest.mark.parametrize("score, expected", [(None, "not measured"), (0.0, "0.00"), (0.15, "0.15")])
def test_session_seed_summary_and_yaml_agree_on_absent_score(score, expected, monkeypatch):
    monkeypatch.setattr(
        "ouroboros.mcp.tools.session_seed_handler.build_session_context_seed",
        lambda _context: SimpleNamespace(seed=_seed(score), gap_questions=()),
    )

    result = handle_session_context_seed({"goal": "Build a local CLI"})

    assert result.is_ok
    text = result.value.content[0].text
    assert f"Ambiguity Score: {expected}" in text
    assert result.value.meta["ambiguity_score"] == score
    data = yaml.safe_load(text.split("--- Seed YAML ---\n", 1)[1])
    assert data["metadata"]["ambiguity_score"] == score
    if score is None:
        assert "conservative ceiling" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("score, expected", [(None, "not measured"), (0.15, "0.15")])
async def test_generate_seed_handler_formats_returned_nullable_seed(score, expected, monkeypatch):
    state = InterviewState(interview_id="interview-nullable", initial_context="Build a local CLI")
    engine = MagicMock()
    engine.load_state = AsyncMock(return_value=Result.ok(state))
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=Result.ok(_seed(score)))
    monkeypatch.setattr(
        "ouroboros.mcp.tools.authoring_handlers.should_dispatch_via_plugin", lambda *_args: False
    )
    monkeypatch.setattr(
        "ouroboros.mcp.tools.authoring_handlers.SeedGenerator", lambda **_kw: generator
    )
    handler = GenerateSeedHandler(interview_engine=engine, llm_adapter=MagicMock())
    # This is the existing scored interview path; only the returned Seed is nullable.
    monkeypatch.setattr(
        GenerateSeedHandler, "_load_stored_ambiguity_score", lambda _self, _state: MagicMock()
    )

    result = await handler.handle({"session_id": state.interview_id})

    assert result.is_ok, result.error if result.is_err else ""
    assert f"Ambiguity Score: {expected}" in result.value.content[0].text
    assert result.value.meta["ambiguity_score"] == score


def test_reviewed_unscored_seed_evolves_with_null_and_parent_lineage():
    data = _seed(None, "reviewed_console_preview").to_dict()
    data["reviewed_preview"] = {"revision": "parent-revision", "evidence": ["user request"]}
    parent = Seed.from_dict(data)
    result = SeedGenerator(llm_adapter=MagicMock()).generate_from_reflect(
        parent,
        ReflectOutput(
            refined_goal="Build a local CLI with filtering",
            refined_constraints=parent.constraints,
            refined_acs=ac_texts(parent.acceptance_criteria),
        ),
    )

    assert result.is_ok, result.error if result.is_err else ""
    child = Seed.from_dict(yaml.safe_load(yaml.safe_dump(result.value.to_dict())))
    assert child.metadata.ambiguity_score is None
    assert child.metadata.parent_seed_id == parent.metadata.seed_id
    assert child.metadata.seed_id != parent.metadata.seed_id
    assert child.metadata.generation_mode != "reviewed_console_preview"
    assert child.metadata.gate_forced is None
    # Plugin-owned extras are historical carryover, not approval of the changed goal.
    assert child.to_dict()["reviewed_preview"] == parent.to_dict()["reviewed_preview"]
    assert "missing_ambiguity_score" in {
        item.code for item in GradeGate().grade_seed(child).blockers
    }
