# #2594: exact legacy registration recognition (bounded follow-up)

Base: df1ecbfbbdd6622ecaafc72a0797170963a08079.

Main already recognizes the plugin bundle's MCP registration. The remaining
legacy user-level helper used a raw substring search for `ouroboros` anywhere
in ~/.claude/mcp.json. An unrelated server named `not-ouroboros`, a reminder
string, malformed JSON or an array containing the word therefore all suppressed
the setup gate and could mark a new user as previously installed.

Four new negative cases failed on unmodified main (4 failed, 56 passed).
Parse the legacy JSON and require the exact server key in an object-shaped
mcpServers map, matching the bundle registration check. This is registration
recognition only: it does not prove the launcher can start, validate credentials,
or change Codex behavior. A correctly named existing empty legacy registration
continues to count, preserving the existing contract rather than adding launch
validation.

Five new focused cases plus existing actual hook-subprocess routing tests:
61 passed locally; changed script/tests Ruff check/format pass. Native Claude
host interaction is not claimed. Fork-only draft; no upstream merge/release.
