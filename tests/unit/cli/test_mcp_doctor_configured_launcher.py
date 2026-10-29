"""#2292: effective configured-launcher resolution, redaction, fixture probes."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ouroboros.cli.commands.mcp_doctor import (
    _configured_launcher_probe_config,
    _local_stdio_probe_config,
    _probe_configured_launcher,
    _read_codex_mcp_server,
    _redact_config_value,
    _redacted_server_config_summary,
)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("OPENAI_API_KEY", "[redacted]"),
        ("mcp_access_token", "[redacted]"),
        ("Authorization", "[redacted]"),
        ("CLIENT_SECRET", "[redacted]"),
        ("db_password", "[redacted]"),
        ("OUROBOROS_HOME", "visible"),
        ("LOG_LEVEL", "debug"),
    ],
)
def test_redact_config_value_masks_secret_keys(key: str, expected: str) -> None:
    value = "visible" if expected == "visible" else ("debug" if expected == "debug" else "s3cr3t")
    assert _redact_config_value(key, value) == (expected if expected == "[redacted]" else value)


def test_redacted_server_config_summary_masks_env(tmp_path: Path) -> None:
    config = _local_stdio_probe_config(tmp_path)
    config.env["OPENAI_API_KEY"] = "sk-live-secret"
    summary = _redacted_server_config_summary(config)
    rendered = json.dumps(summary)
    assert "sk-live-secret" not in rendered
    assert summary["env"] == "[omitted]"
    assert summary["command"] == "[omitted]"


def _write_config(codex_home: Path, body: str) -> Path:
    codex_home.mkdir(parents=True, exist_ok=True)
    config_path = codex_home / "config.toml"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def test_read_codex_mcp_server_missing_config(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _read_codex_mcp_server(tmp_path, "ouroboros")


def test_read_codex_mcp_server_malformed_toml(tmp_path: Path) -> None:
    _write_config(tmp_path, "[mcp_servers.ouroboros\ncommand =")
    import tomllib

    with pytest.raises(tomllib.TOMLDecodeError):
        _read_codex_mcp_server(tmp_path, "ouroboros")


def test_read_codex_mcp_server_missing_entry(tmp_path: Path) -> None:
    _write_config(tmp_path, '[mcp_servers.other]\ncommand = "x"\n')
    with pytest.raises(KeyError):
        _read_codex_mcp_server(tmp_path, "ouroboros")


def test_read_codex_mcp_server_entry_without_command(tmp_path: Path) -> None:
    _write_config(tmp_path, '[mcp_servers.ouroboros]\nargs = ["serve"]\n')
    with pytest.raises(ValueError, match="no command"):
        _read_codex_mcp_server(tmp_path, "ouroboros")


def test_configured_launcher_probe_config_parses_entry(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "[mcp_servers.ouroboros]\n"
        'command = "/bin/echo"\n'
        'args = ["a", "b"]\n'
        "startup_timeout_sec = 3.5\n"
        "[mcp_servers.ouroboros.env]\n"
        'OUROBOROS_HOME = "/tmp/home"\n',
    )
    config = _configured_launcher_probe_config(tmp_path, "ouroboros")
    assert config.command == "/bin/echo"
    assert config.args == ("a", "b")
    assert config.timeout == 3.5
    assert config.env["OUROBOROS_HOME"] == "/tmp/home"


async def test_probe_configured_launcher_warns_when_config_missing(tmp_path: Path) -> None:
    results = await _probe_configured_launcher(tmp_path, "ouroboros", fixture_probe=True)
    assert len(results) == 1
    assert results[0].status == "warn"
    assert results[0].name == "configured_launcher_resolution"


async def test_probe_configured_launcher_fails_on_malformed_toml(tmp_path: Path) -> None:
    _write_config(tmp_path, "[mcp_servers.ouroboros\ncommand =")
    results = await _probe_configured_launcher(tmp_path, "ouroboros", fixture_probe=True)
    assert len(results) == 1
    assert results[0].status == "fail"
    assert "malformed" in results[0].message


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


def _fake_adapter(connect_error: str | None):
    from types import SimpleNamespace

    from ouroboros.cli.commands.mcp_doctor import _expected_ouroboros_tool_names
    from ouroboros.core.types import Result

    class _Adapter:
        def __init__(self, **_kwargs) -> None:
            self.transport_entered = connect_error is None
            self.server_snapshot = None if connect_error else SimpleNamespace()
            self.protocol_version = "" if connect_error else "2025-06-18"

        async def connect(self, _config):
            if connect_error is not None:
                return Result.err(connect_error)
            return Result.ok(True)

        async def list_tools(self):
            return Result.ok([_FakeTool(name) for name in _expected_ouroboros_tool_names()])

        async def disconnect(self):
            return Result.ok(True)

    return _Adapter


async def test_probe_configured_launcher_reports_startup_failure(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        '[mcp_servers.ouroboros]\ncommand = "/nonexistent/ouroboros-mcp"\n',
    )
    with patch(
        "ouroboros.cli.commands.mcp_doctor.MCPClientAdapter",
        _fake_adapter("spawn failed: /nonexistent/ouroboros-mcp"),
    ):
        results = await _probe_configured_launcher(tmp_path, "ouroboros", fixture_probe=True)
    statuses = {result.name: result.status for result in results}
    assert statuses["configured_launcher_resolution"] == "pass"
    assert statuses["configured_stdio_startup_transport"] == "fail"
    startup = next(r for r in results if r.name == "configured_stdio_startup_transport")
    assert "spawn failed" not in startup.message


async def test_probe_configured_launcher_fixture_success_redacts_secrets(
    tmp_path: Path,
) -> None:
    server_home = tmp_path / "server-home"
    server_home.mkdir()
    fixture = _local_stdio_probe_config(server_home)
    args_toml = ", ".join(json.dumps(arg) for arg in fixture.args)
    env_toml = "\n".join(f"{key} = {json.dumps(value)}" for key, value in fixture.env.items())
    codex_home = tmp_path / "codex-home"
    _write_config(
        codex_home,
        "[mcp_servers.ouroboros]\n"
        f"command = {json.dumps(sys.executable)}\n"
        f"args = [{args_toml}]\n"
        "[mcp_servers.ouroboros.env]\n"
        f"{env_toml}\n"
        'OPENAI_API_KEY = "sk-fixture-secret"\n',
    )
    with patch(
        "ouroboros.cli.commands.mcp_doctor.MCPClientAdapter",
        _fake_adapter(None),
    ):
        results = await _probe_configured_launcher(codex_home, "ouroboros", fixture_probe=True)
    by_name = {result.name: result for result in results}
    assert by_name["configured_launcher_resolution"].status == "pass"
    assert by_name["configured_stdio_startup_transport"].status == "pass"
    assert by_name["configured_stdio_protocol_discovery"].status == "pass"
    assert by_name["configured_stdio_tool_recognition"].status == "pass"
    all_messages = " ".join(result.message for result in results)
    assert "sk-fixture-secret" not in all_messages
    assert "[omitted]" in by_name["configured_launcher_resolution"].message


async def test_probe_default_does_not_execute_fixture(tmp_path: Path) -> None:
    with patch("ouroboros.cli.commands.mcp_doctor.MCPClientAdapter") as adapter:
        result = await _probe_configured_launcher(tmp_path)
    adapter.assert_not_called()
    assert result[0].status == "warn"


@pytest.mark.parametrize("failure", ["returned", "raised", "cleanup_returned", "cleanup_raised"])
async def test_output_omits_echoed_config_secrets(tmp_path: Path, failure: str) -> None:
    from dataclasses import asdict

    from ouroboros.cli.commands.mcp_doctor import CheckResult
    from ouroboros.core.types import Result

    secret = "fixture-secret-DO-NOT-PRINT"
    _write_config(
        tmp_path,
        "[mcp_servers.ouroboros]\n"
        f'command = "https://user:{secret}@example.invalid"\n'
        f'args = ["--token", "{secret}"]\n'
        "[mcp_servers.ouroboros.env]\n"
        f'OPENAI_API_KEY = "{secret}"\n',
    )
    adapter = MagicMock()
    adapter.disconnect = AsyncMock(return_value=Result.ok(True))
    if failure == "cleanup_returned":
        adapter.disconnect.return_value = Result.err(secret)
    if failure == "cleanup_raised":
        adapter.disconnect.side_effect = RuntimeError(secret)
    collect = AsyncMock(
        return_value=[CheckResult("local_stdio_startup_transport", "fail", secret, secret)]
    )
    if failure == "raised":
        collect.side_effect = RuntimeError(secret)
    with (
        patch("ouroboros.cli.commands.mcp_doctor.MCPClientAdapter", return_value=adapter),
        patch("ouroboros.cli.commands.mcp_doctor._collect_local_stdio_results", collect),
    ):
        results = await _probe_configured_launcher(tmp_path, fixture_probe=True)
    serialized = json.dumps([asdict(result) for result in results])
    assert secret not in serialized
    assert "https://user:" not in serialized
    assert "--token" not in serialized
    assert any(result.status == "fail" for result in results)


async def test_malformed_config_exception_values_are_omitted(tmp_path: Path) -> None:
    from dataclasses import asdict

    secret = "fixture-malformed-secret"
    with patch(
        "ouroboros.cli.commands.mcp_doctor._configured_launcher_probe_config",
        side_effect=ValueError(secret),
    ):
        results = await _probe_configured_launcher(tmp_path, fixture_probe=True)
    assert results[0].status == "fail"
    assert secret not in json.dumps([asdict(result) for result in results])


@pytest.mark.parametrize(
    "fields",
    [
        'command = ["python", "server"]',
        "command = 42",
        "command = true",
        'command = ""',
        'command = "   "',
        'command = "fixture"\nargs = [1, true]',
        'command = "fixture"\nargs = "--serve"',
        'command = "fixture"\nargs = false',
        'command = "fixture"\nenv = { TOKEN = 42 }',
        'command = "fixture"\nenv = { TOKEN = true }',
        'command = "fixture"\nenv = false',
        'command = "fixture"\nstartup_timeout_sec = nan',
        'command = "fixture"\nstartup_timeout_sec = inf',
        'command = "fixture"\nstartup_timeout_sec = -inf',
        'command = "fixture"\nstartup_timeout_sec = -1',
        'command = "fixture"\nstartup_timeout_sec = 0',
        'command = "fixture"\nstartup_timeout_sec = true',
        'command = "fixture"\nstartup_timeout_sec = "5"',
        'command = "fixture"\ntimeout = nan',
    ],
)
async def test_invalid_launcher_types_fail_before_adapter_construction(
    tmp_path: Path, fields: str
) -> None:
    _write_config(tmp_path, "[mcp_servers.ouroboros]\n" + fields + "\n")
    with pytest.raises(ValueError):
        _configured_launcher_probe_config(tmp_path)
    with patch("ouroboros.cli.commands.mcp_doctor.MCPClientAdapter") as adapter:
        results = await _probe_configured_launcher(tmp_path, fixture_probe=True)
    adapter.assert_not_called()
    assert results[0].status == "fail"


@pytest.mark.parametrize("timeout", [1, 0.25, 15.0])
def test_finite_positive_timeout_preserves_valid_string_values(tmp_path: Path, timeout) -> None:
    _write_config(
        tmp_path,
        '[mcp_servers.ouroboros]\ncommand = "fixture"\nargs = ["--token", ""]\n'
        f"startup_timeout_sec = {timeout}\n"
        'env = { TOKEN = "fixture-value", EMPTY = "" }\n',
    )
    config = _configured_launcher_probe_config(tmp_path)
    assert config.command == "fixture"
    assert config.args == ("--token", "")
    assert config.env == {"TOKEN": "fixture-value", "EMPTY": ""}
    assert config.timeout == float(timeout)
