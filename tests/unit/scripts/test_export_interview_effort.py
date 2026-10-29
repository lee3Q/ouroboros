"""Read-only and privacy checks for the partial #1657 exporter."""

import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "export_interview_effort.py"
spec = importlib.util.spec_from_file_location("effort", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE events(id TEXT,aggregate_type TEXT,aggregate_id TEXT,"
        "event_type TEXT,payload TEXT,timestamp TEXT)"
    )
    return connection


def add(connection, count, *, identity="private-id", kind="interview.response.recorded"):
    connection.execute(
        "INSERT INTO events VALUES (?, 'interview', ?, ?, ?, '2026-10-29')",
        (str(connection.total_changes), identity, kind, json.dumps(count)),
    )


def test_exact_counts_not_preview_or_decision_inference():
    with database() as connection:
        add(connection, {"response_chars": 900, "response_preview": "SECRET"})
        add(connection, {"response_chars": 0})
        add(connection, {"response_chars": 42}, kind="interview.completed")
        records = module.export_counts(connection)
    assert len(records) == 1
    assert records[0]["response_chars_total"] == 900
    assert records[0]["recorded_response_events"] == 2
    assert records[0]["unknown_response_events"] == 0
    assert "SECRET" not in str(records)
    assert "private-id" not in str(records)
    assert set(records[0]) == {
        "interview_id_sha256",
        "recorded_response_events",
        "known_response_chars",
        "unknown_response_events",
        "response_chars_total",
    }


@pytest.mark.parametrize("bad", [None, True, False, -1, 1.5, "900", [], {}])
def test_unknown_counts_do_not_become_zero_or_preview_length(bad):
    with database() as connection:
        add(connection, {"response_chars": 12})
        add(connection, {"response_chars": bad, "response_preview": "x" * 200})
        record = module.export_counts(connection)[0]
    assert record["response_chars_total"] is None
    assert record["known_response_chars"] == 12
    assert record["unknown_response_events"] == 1


def test_legacy_and_malformed_rows_stay_unknown():
    with database() as connection:
        add(connection, {"response_preview": "short"})
        connection.execute("UPDATE events SET payload = 'not json'")
        assert module.export_counts(connection)[0]["response_chars_total"] is None


def test_sessions_are_separate():
    with database() as connection:
        add(connection, {"response_chars": 2}, identity="a")
        add(connection, {"response_chars": 3}, identity="b")
        records = module.export_counts(connection)
    assert {r["response_chars_total"] for r in records} == {2, 3}
    assert len({r["interview_id_sha256"] for r in records}) == 2


def test_cli_does_not_create_missing_database(tmp_path):
    path = tmp_path / "missing.db"
    result = subprocess.run([sys.executable, str(SCRIPT), "--db", str(path)], capture_output=True)
    assert result.returncode == 2
    assert not path.exists()
    assert result.stdout == b""


def test_cli_leaves_database_bytes_unchanged(tmp_path):
    path = tmp_path / "events.db"
    with database() as source, sqlite3.connect(path) as target:
        add(source, {"response_chars": 77, "response_preview": "SECRET"})
        source.commit()
        source.backup(target)
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["response_chars_total"] == 77
    assert "SECRET" not in result.stdout
    assert path.read_bytes() == before
