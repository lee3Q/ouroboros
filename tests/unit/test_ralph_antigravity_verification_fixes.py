"""Regression tests for Ralph/Antigravity verification deadlock, runtime LLM fallback, and distillation bounds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ouroboros.auto.safe_defaults import _SAFE_DEFAULTS
from ouroboros.bigbang.interview import InterviewRound, InterviewState
from ouroboros.bigbang.requirement_distillation import build_requirement_distillation
from ouroboros.evaluation.artifact_collector import ArtifactCollector
from ouroboros.evaluation.detector import _collect_manifests, _validate_proposal
from ouroboros.interview_adapters.models import ReferenceCue, ReferenceOrigin
from ouroboros.interview_adapters.reference_contrast import candidates_from_contrast_answer
from ouroboros.orchestrator.antigravity_cli_runtime import AntigravityCLIRuntime


def test_artifact_collector_extracts_file_uri_and_skips_eval_scratch_file(tmp_path: Path) -> None:
    """Antigravity file:// markdown links are extracted and .ouroboros_eval_artifact.md is excluded."""
    src_dir = tmp_path / "src" / "aml"
    src_dir.mkdir(parents=True)
    engine_py = src_dir / "engine.py"
    engine_py.write_text("def run_engine() -> int:\n    return 42\n", encoding="utf-8")

    eval_scratch = tmp_path / ".ouroboros_eval_artifact.md"
    eval_scratch.write_text("# Summary only\n", encoding="utf-8")

    output = (
        f"Implemented [`engine.py`](file://{engine_py}#L1-L2) and "
        f"[scratch](file://{eval_scratch})."
    )
    bundle = ArtifactCollector().collect(output, str(tmp_path))

    collected_paths = [Path(f.file_path).resolve() for f in bundle.files]
    assert engine_py.resolve() in collected_paths
    assert eval_scratch.resolve() not in collected_paths


def test_artifact_collector_scan_directory_skips_eval_scratch_file(tmp_path: Path) -> None:
    """Directory scan fallback never collects .ouroboros_eval_artifact.md."""
    code_file = tmp_path / "cli.py"
    code_file.write_text("print('ok')\n", encoding="utf-8")
    eval_scratch = tmp_path / ".ouroboros_eval_artifact.md"
    eval_scratch.write_text("# Summary scratch\n", encoding="utf-8")

    bundle = ArtifactCollector().collect("No explicit paths in output", str(tmp_path))
    collected_names = [Path(f.file_path).name for f in bundle.files]
    assert "cli.py" in collected_names
    assert ".ouroboros_eval_artifact.md" not in collected_names


def test_detector_collect_manifests_detects_greenfield_python_stdlib_unittest_layout(
    tmp_path: Path,
) -> None:
    """Greenfield Python stdlib projects without pyproject.toml still produce a unittest manifest cue."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_engine.py").write_text(
        "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n",
        encoding="utf-8",
    )

    manifests = _collect_manifests(tmp_path)
    assert "<python-stdlib-unittest-layout>" in manifests
    assert "python3 -m unittest discover -s tests" in manifests["<python-stdlib-unittest-layout>"]

    validated = _validate_proposal(tmp_path, {"test": "python3 -m unittest discover -s tests"})
    assert validated.test == "python3 -m unittest discover -s tests"


def test_antigravity_cli_runtime_guards_non_llm_backend_and_enriches_token_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AntigravityCLIRuntime falls back to default LLM backend when passed 'antigravity' and estimates tokens."""
    fake_cli = tmp_path / "agy"
    fake_cli.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    fake_cli.chmod(0o755)

    runtime = AntigravityCLIRuntime(
        cli_path=fake_cli,
        cwd=tmp_path,
        llm_backend="antigravity",
    )
    assert runtime.llm_backend == "claude_code"

    result_data: dict[str, Any] = {"subtype": "success", "returncode": 0}
    runtime._enrich_terminal_result_data(
        result_data,
        prompt="abcd" * 25,
        final_message="efgh" * 10,
    )
    assert result_data["estimated_tokens"] == 35
    assert result_data["usage"] == {
        "input_tokens": 25,
        "output_tokens": 10,
        "total_tokens": 35,
        "estimated": True,
    }


def test_distill_requirement_ledger_bounds_long_text_over_8000_chars() -> None:
    """RequirementEvidence and RequirementCandidate truncate text > 8000 chars without ValidationError."""
    long_context = "A" * 9500
    long_answer = "Must support deterministic AST mutation. " + ("B" * 9000)
    cue = ReferenceCue(
        reference_id="ref-1",
        label="design.md",
        origin=ReferenceOrigin.FILE_REFERENCE,
        excerpt="C" * 1900,
    )
    state = InterviewState(
        interview_id="int-bound-test",
        initial_context=long_context,
        rounds=[
            InterviewRound(
                round_number=1,
                question="What are the core requirements?",
                user_response=long_answer,
            )
        ],
        reference_cues=[cue],
    )

    ledger = build_requirement_distillation(state)
    assert all(len(ev.text) <= 8000 for ev in ledger.evidence)
    assert all(len(cand.text) <= 8000 for cand in ledger.candidates)

    contrast_ev, contrast_cand = candidates_from_contrast_answer(
        cue=cue,
        answer="D" * 9100,
    )
    assert len(contrast_ev.text) == 8000
    assert len(contrast_cand.text) == 8000


def test_safe_defaults_preserve_explicit_goal_deliverables() -> None:
    """Safe defaults for outputs and constraints explicitly preserve goal deliverables."""
    assert "Preserve all deliverables explicitly requested in the goal" in _SAFE_DEFAULTS["outputs"].value
    assert (
        "Preserve all deliverables and surfaces explicitly requested in the goal"
        in _SAFE_DEFAULTS["constraints"].value
    )
