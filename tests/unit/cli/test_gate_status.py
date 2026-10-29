"""Local provenance counts must not turn unknown history into gate success."""

from pathlib import Path

from typer.testing import CliRunner
import yaml

from ouroboros.cli.commands.gate_status import summarize_gate_decisions
from ouroboros.cli.commands.status import app


def seed(directory: Path, name: str, seed_id: str, **metadata: object) -> None:
    (directory / name).write_text(
        yaml.safe_dump({"metadata": {"seed_id": seed_id, **metadata}}), encoding="utf-8"
    )


def test_counts_unique_recorded_decisions_and_keeps_legacy_unknown(tmp_path: Path) -> None:
    seed(tmp_path, "a.yaml", "a", gate_forced=True, ambiguity_score=0.1)
    seed(tmp_path, "copy.json", "a", gate_forced=True)
    seed(tmp_path, "b.yml", "b", gate_forced=False, ambiguity_score=0.9)
    seed(tmp_path, "old.yaml", "old", ambiguity_score=0.9)
    result = summarize_gate_decisions(tmp_path)
    assert (result.forced, result.gated, result.unknown, result.unreadable) == (1, 1, 1, 0)
    assert "50.0%" in result.render()


def test_conflicts_and_non_boolean_markers_are_unknown(tmp_path: Path) -> None:
    seed(tmp_path, "a.yaml", "a", gate_forced=True)
    seed(tmp_path, "b.yaml", "a", gate_forced=False)
    seed(tmp_path, "c.yaml", "a", gate_forced=True)
    seed(tmp_path, "text.yaml", "text", gate_forced="false")
    result = summarize_gate_decisions(tmp_path)
    assert (result.forced, result.gated, result.unknown) == (0, 0, 2)
    assert "unavailable" in result.render()


def test_unreadable_and_non_seed_documents_excluded(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("{", encoding="utf-8")
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    (tmp_path / "encoding.yaml").write_bytes(b"\xff")
    (tmp_path / "notes.txt").write_text("irrelevant", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    seed(tmp_path / "nested", "ignored.yaml", "nested", gate_forced=True)
    assert summarize_gate_decisions(tmp_path).unreadable == 3


def test_cli_is_read_only_and_names_denominator(tmp_path: Path) -> None:
    seed(tmp_path, "a.yaml", "a", gate_forced=True)
    before = (tmp_path / "a.yaml").read_bytes()
    result = CliRunner().invoke(app, ["ambiguity-gate", "--seed-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Forced: 1" in result.output
    assert "100.0%" in result.output
    assert "No telemetry sent" in result.output
    assert (tmp_path / "a.yaml").read_bytes() == before


def test_missing_directory_fails_instead_of_reporting_zero(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["ambiguity-gate", "--seed-dir", str(tmp_path / "missing")])
    assert result.exit_code == 1
    assert "Cannot read Seed directory" in result.output


def test_coverage_and_symlinks_do_not_read_outside_directory(tmp_path: Path) -> None:
    seed(tmp_path, "known.yaml", "known", gate_forced=True)
    seed(tmp_path, "old.yaml", "old")
    (tmp_path / "link.yaml").symlink_to(tmp_path / "known.yaml")
    result = summarize_gate_decisions(tmp_path)
    assert result.unreadable == 1
    assert "Unique Seed IDs: 2" in result.render()
    assert "Recorded-decision coverage: 50.0%" in result.render()
