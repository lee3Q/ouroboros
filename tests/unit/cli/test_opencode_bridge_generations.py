"""Bridge cleanup recognizes V1 and manually migrated V2 registrations.

These tests do not claim V2 plugin runtime compatibility.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ouroboros.cli.commands.setup import _cleanup_plugin_artifacts
from ouroboros.cli.commands.uninstall import _remove_opencode_bridge_plugin
from ouroboros.cli.opencode_config import is_bridge_plugin_entry


@pytest.mark.parametrize(
    "entry",
    [
        "/old/plugins/ouroboros-bridge/ouroboros-bridge.ts",
        "/old/plugins/ouroboros-bridge",
        "/old/plugins/ouroboros-bridge/",
        "/old/plugins/ouroboros-bridge/index.ts",
        "/old/plugins/ouroboros-bridge/index.js",
        r"C:\old\plugins\ouroboros-bridge",
        r"C:\old\plugins\ouroboros-bridge\index.ts",
    ],
)
def test_bridge_identity_across_generations(entry: str) -> None:
    assert is_bridge_plugin_entry(entry)


@pytest.mark.parametrize(
    "entry",
    [
        None,
        {},
        4,
        "",
        "@vendor/ouroboros-bridge",
        "/plugins/other/index.ts",
        "/plugins/ouroboros-bridge-copy/index.ts",
        "/plugins/ouroboros-bridge/other.ts",
        "/plugins/ouroboros-bridge/nested/index.ts",
        "/not-plugins/ouroboros-bridge",
    ],
)
def test_bridge_identity_does_not_capture_other_plugins(entry: object) -> None:
    assert not is_bridge_plugin_entry(entry)


@pytest.mark.parametrize("cleanup", ["uninstall", "switch"])
@pytest.mark.parametrize("suffix", ["json", "jsonc"])
def test_cleanup_removes_both_keys_and_preserves_unrelated_data(
    tmp_path: Path, cleanup: str, suffix: str
) -> None:
    path = tmp_path / f"opencode.{suffix}"
    data = {
        "plugin": ["/old/plugins/ouroboros-bridge/ouroboros-bridge.ts", "keep-v1"],
        "plugins": [
            "/old/plugins/ouroboros-bridge",
            "/old/plugins/ouroboros-bridge/index.js",
            "keep-v2",
        ],
        "mcp": {"unrelated": {"enabled": True}},
    }
    original = "// comment\n" + json.dumps(data)
    path.write_text(original)
    owner = "setup" if cleanup == "switch" else "uninstall"
    with (
        patch(f"ouroboros.cli.commands.{owner}.opencode_config_dir", return_value=tmp_path),
        patch(f"ouroboros.cli.commands.{owner}.find_opencode_config", return_value=path),
        patch("ouroboros.cli.commands.setup.print_warning") as warning,
    ):
        if cleanup == "switch":
            _cleanup_plugin_artifacts()
        else:
            assert _remove_opencode_bridge_plugin(dry_run=False)
    assert json.loads(path.read_text()) == {
        "plugin": ["keep-v1"],
        "plugins": ["keep-v2"],
        "mcp": data["mcp"],
    }
    assert warning.call_count == 1


def test_v2_uninstall_dry_run_preserves_config_and_plugin_directory(tmp_path: Path) -> None:
    path = tmp_path / "opencode.json"
    path.write_text('{"plugins":["/old/plugins/ouroboros-bridge"]}')
    original = path.read_bytes()
    plugin = tmp_path / "plugins/ouroboros-bridge"
    plugin.mkdir(parents=True)
    index = plugin / "index.ts"
    index.write_text("fixture")
    with (
        patch("ouroboros.cli.commands.uninstall.opencode_config_dir", return_value=tmp_path),
        patch("ouroboros.cli.commands.uninstall.find_opencode_config", return_value=path),
    ):
        assert _remove_opencode_bridge_plugin(dry_run=True)
    assert path.read_bytes() == original
    assert index.read_text() == "fixture"


@pytest.mark.parametrize("cleanup", ["uninstall", "switch"])
def test_malformed_generation_key_is_preserved_while_other_is_cleaned(
    tmp_path: Path, cleanup: str
) -> None:
    path = tmp_path / "opencode.json"
    data = {"plugin": {"custom": True}, "plugins": ["/old/plugins/ouroboros-bridge", "keep"]}
    path.write_text(json.dumps(data))
    owner = "setup" if cleanup == "switch" else "uninstall"
    with (
        patch(f"ouroboros.cli.commands.{owner}.opencode_config_dir", return_value=tmp_path),
        patch(f"ouroboros.cli.commands.{owner}.find_opencode_config", return_value=path),
    ):
        if cleanup == "switch":
            _cleanup_plugin_artifacts()
        else:
            assert _remove_opencode_bridge_plugin(dry_run=False)
    assert json.loads(path.read_text()) == {"plugin": data["plugin"], "plugins": ["keep"]}


@pytest.mark.parametrize("cleanup", ["uninstall", "switch"])
def test_cleanup_without_bridge_is_byte_preserving(tmp_path: Path, cleanup: str) -> None:
    path = tmp_path / "opencode.json"
    path.write_text('// keep comment\n{"plugin":["other"],"plugins":["other-v2"]}')
    original = path.read_bytes()
    owner = "setup" if cleanup == "switch" else "uninstall"
    with (
        patch(f"ouroboros.cli.commands.{owner}.opencode_config_dir", return_value=tmp_path),
        patch(f"ouroboros.cli.commands.{owner}.find_opencode_config", return_value=path),
        patch("ouroboros.cli.commands.setup._atomic_write_text") as write,
    ):
        if cleanup == "switch":
            _cleanup_plugin_artifacts()
        else:
            assert not _remove_opencode_bridge_plugin(dry_run=False)
    write.assert_not_called()
    assert path.read_bytes() == original


@pytest.mark.parametrize("cleanup", ["uninstall", "switch"])
def test_cleanup_atomic_write_failure_preserves_config(tmp_path: Path, cleanup: str) -> None:
    path = tmp_path / "opencode.json"
    path.write_text('{"plugins":["/old/plugins/ouroboros-bridge"]}')
    original = path.read_bytes()
    owner = "setup" if cleanup == "switch" else "uninstall"
    with (
        patch(f"ouroboros.cli.commands.{owner}.opencode_config_dir", return_value=tmp_path),
        patch(f"ouroboros.cli.commands.{owner}.find_opencode_config", return_value=path),
        patch("ouroboros.cli.commands.setup._atomic_write_text", side_effect=OSError("read only")),
    ):
        if cleanup == "switch":
            _cleanup_plugin_artifacts()
        else:
            assert not _remove_opencode_bridge_plugin(dry_run=False)
    assert path.read_bytes() == original


def test_public_uninstall_preview_finds_v2_config_without_plugin_directory(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from ouroboros.cli.commands.uninstall import app

    path = tmp_path / "opencode.json"
    path.write_text('{"plugins":["/old/plugins/ouroboros-bridge"]}')
    original = path.read_bytes()
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("pathlib.Path.cwd", return_value=tmp_path),
        patch("ouroboros.cli.commands.uninstall.opencode_config_dir", return_value=tmp_path),
        patch("ouroboros.cli.commands.uninstall.find_opencode_config", return_value=path),
    ):
        result = CliRunner().invoke(app, ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert "OpenCode bridge plugin entry" in result.output
    assert path.read_bytes() == original


@pytest.mark.parametrize("value", [None, [], "text", 123, True])
@pytest.mark.parametrize("mode", ["uninstall", "switch", "preview"])
def test_non_object_config_is_best_effort_and_byte_preserving(
    tmp_path: Path, value: object, mode: str
) -> None:
    from typer.testing import CliRunner

    from ouroboros.cli.commands.uninstall import _remove_opencode_mcp, app

    path = tmp_path / "opencode.json"
    path.write_text(json.dumps(value))
    original = path.read_bytes()
    owner = "setup" if mode == "switch" else "uninstall"
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("pathlib.Path.cwd", return_value=tmp_path),
        patch(f"ouroboros.cli.commands.{owner}.opencode_config_dir", return_value=tmp_path),
        patch(f"ouroboros.cli.commands.{owner}.find_opencode_config", return_value=path),
    ):
        if mode == "switch":
            _cleanup_plugin_artifacts()
        elif mode == "uninstall":
            assert not _remove_opencode_bridge_plugin(dry_run=False)
            assert not _remove_opencode_mcp(dry_run=False)
        else:
            result = CliRunner().invoke(app, ["--dry-run"])
            assert result.exit_code == 0, result.output
    assert path.read_bytes() == original
