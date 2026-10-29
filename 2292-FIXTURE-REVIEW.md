# #2292 configured-launcher fixture candidate

Base: c72d0b2d73ee5786f5abf0a56371bb9f096c00c6.

This is not a complete doctor integration. It adds lower-level config parsing and an explicitly enabled controlled-fixture probe. Default calls return a warning without reading or executing launcher configuration. No CLI wiring or effective CODEX_HOME selection is provided.

The parser accepts only a nonempty string command, list of string arguments, string-to-string environment map and finite positive numeric timeout excluding booleans. It never coerces malformed values. Returned diagnostics omit caller-controlled commands, arguments, environment values, tool names and arbitrary adapter output. This does not establish redaction of lower-level SDK stderr or logs. The fixture flag is not a sandbox and must never be used with an untrusted launcher.

Independent clean-base verification: 45 tests passed. Ruff check and format passed for both Python files. Nine additional malformed-config cases rejected with ValueError, without constructing an adapter or launching a process. No user's configured launcher was executed.

The earlier v2 parser accepted malformed/coerced command, argument and timeout values. That candidate is superseded. These findings were corrected in San's v3 patch, SHA256 006ea39cfc492430664e1d56d85a85b9eac8e1a5de7120dcc95aa2f9ca4c4f7d.

Argon review of this exact candidate has not run. The user removed the Gemini review requirement for Ouroboros on October 29, 2026. This is a scope decision, not completed Gemini review or approval. Final Codex judgment remains with the user. Do not call the issue fixed, merge upstream, close the issue or release from this candidate.
