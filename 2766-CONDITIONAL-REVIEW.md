# PR #2766: conditional B dependency candidate

Fork-only candidate, not an approved dependency-policy change. Do not infer a merge-ready or full compatibility verdict.

Published base: `c72d0b2d73ee5786f5abf0a56371bb9f096c00c6`. Initial local test base: `90cde708732c76e41e7af6e15786bb33c265afdf`.
Upstream PR: https://github.com/Q00/ouroboros/pull/2766

This includes the full dependency bump plus San's conditional pin/install/workflow synchronization patch. It is separate from the other dependency candidate. The two candidates conflict in pyproject.toml and uv.lock and have not been combined. Choosing MCP 1 versus MCP 2 policy is still an explicit final review decision.

Independent local Linux Python 3.14.9 run on this base plus PR and patch: `tests/unit/test_dependencies_configured.py tests/unit/scripts/test_install_runtime_selection.py`: **149 passed**. This used an existing test environment and is a source/pin/install-test result, not a fresh install of this candidate's SDK/MCP dependency graph. No real SDK-to-MCP session, Windows run or remote CI was completed here.

San separately reported installed-profile smoke/import/version checks. His full 149-test runs preceded the final tips: #2766 ended with a comment-only change then 23 pin tests; #2765 ended with workflow-only changes and manually transcribed heredoc checks. The workflow commands were not mechanically extracted and executed in that earlier evidence. Check names still mention MCP 1; a relationship to required-check settings was not verified. These limitations remain and are not erased by this draft.

No upstream merge, formal review, issue closure or release was performed. The user's Codex review retains final judgment. Other open PRs have not all been combined with this tree.
