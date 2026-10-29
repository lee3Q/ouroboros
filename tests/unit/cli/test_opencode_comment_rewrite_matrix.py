"""Pin issue #2530's content-based warnings across every config rewrite path."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from ouroboros.cli.commands import setup, uninstall


@pytest.mark.parametrize("suffix", [".json", ".jsonc"])
@pytest.mark.parametrize("comment", ["// owner note\n", "/* owner note */\n"])
@pytest.mark.parametrize("operation", ["setup_mcp", "setup_bridge", "remove_mcp", "remove_bridge"])
def test_comment_warning_precedes_every_opencode_config_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, comment: str, operation: str
) -> None:
    config_dir = tmp_path / "opencode"
    config_dir.mkdir()
    config_path = config_dir / f"opencode{suffix}"
    bridge_path = str(config_dir / "plugins" / "ouroboros-bridge" / setup._BRIDGE_PLUGIN_FILENAME)
    data = {
        "url": "https://example.com/*literal*/",
        "mcp": {"ouroboros": {"type": "local", "command": ["old"]}},
        "plugin": [bridge_path] if operation == "remove_bridge" else [],
    }
    original = "{\n" + comment + json.dumps(data)[1:]
    config_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(setup, "_find_opencode_config", lambda: config_path)
    monkeypatch.setattr(uninstall, "_find_opencode_config", lambda: config_path)
    monkeypatch.setattr(uninstall, "find_opencode_config", lambda **_kwargs: config_path)
    monkeypatch.setattr(setup, "opencode_config_dir", lambda: config_dir)
    monkeypatch.setattr(uninstall, "opencode_config_dir", lambda: config_dir)
    monkeypatch.setattr(
        setup,
        "_detect_opencode_mcp_command",
        lambda: {"command": ["ouroboros", "mcp", "serve"]},
    )

    def before_rewrite(_message: str) -> None:
        assert config_path.read_text(encoding="utf-8") == original

    warning = Mock(side_effect=before_rewrite)
    monkeypatch.setattr(setup, "print_warning", warning)
    if operation == "setup_mcp":
        setup._ensure_opencode_mcp_entry()
    elif operation == "setup_bridge":
        assert setup._ensure_opencode_plugin_entry()
    elif operation == "remove_mcp":
        assert uninstall._remove_opencode_mcp(dry_run=False)
    else:
        assert uninstall._remove_opencode_bridge_plugin(dry_run=False)

    warning.assert_called_once_with(
        f"Note: JSONC comments in {config_path} were removed during config update."
    )
    rewritten = json.loads(config_path.read_text(encoding="utf-8"))
    assert rewritten["url"] == data["url"]
    assert "owner note" not in config_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("suffix", [".json", ".jsonc"])
def test_comment_markers_in_json_strings_do_not_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    warning = Mock()
    monkeypatch.setattr(setup, "print_warning", warning)
    setup._warn_if_opencode_jsonc_comments_removed(
        tmp_path / f"opencode{suffix}",
        json.dumps({"url": "https://example.com/*literal*/", "note": "// literal"}),
    )
    warning.assert_not_called()
