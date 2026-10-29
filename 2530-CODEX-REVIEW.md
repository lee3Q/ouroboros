# Issue #2530: OpenCode comment-warning regression matrix

Fork-only test draft. The current production code already contains the fix, so this draft does not add a duplicate production implementation or claim to preserve comments. It pins warnings before a rewrite that removes comments.

Issue: https://github.com/Q00/ouroboros/issues/2530
Actual base: `c72d0b2d73ee5786f5abf0a56371bb9f096c00c6`.

## Requirement-to-source audit

`setup._warn_if_opencode_jsonc_comments_removed` strips quoted strings before detecting `//` or `/*`, without checking the filename extension. It is already called before writes in setup MCP registration, setup bridge registration, uninstall MCP removal and uninstall bridge removal. No setup.py/uninstall.py edits are needed for that behavior on this base.

The new test file exercises both `.json` and `.jsonc`, line and block comments, and all four rewrite paths. Each case asserts that the original file still exists unchanged when the warning is emitted, the exact path is named, the rewrite succeeds, and URL/comment-like string data survives. Two additional cases reject false warnings for markers inside JSON strings.

## Independent verification

Linux, Python 3.14.9, existing environment with `PYTHONPATH=src`:

- New matrix: 18 tests passed.
- Matrix plus existing config-selection tests: **33 passed**.
- Existing complete `test_setup.py` and `test_uninstall.py`: **506 passed, 4 skipped**.
- CI-pinned Ruff 0.17.0 check and format check on the new file passed.

All operations use temporary config paths. No real user config or bridge installation was changed by the tests. No native Windows, real OpenCode 2 host, remote CI, or complete setup/uninstall end-to-end run was completed. OpenCode 2 bridge migration (#2529) is separate and remains unresolved. The skip results and scope limits are not a whole-issue closure or merge verdict. No upstream interaction or release was performed; the user's Codex review retains final judgment.
