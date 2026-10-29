# #2441: type-exact plugin option defaults (bounded follow-up)

Base: df1ecbfbbdd6622ecaafc72a0797170963a08079.

Current main already rejects non-default checkpoint/recovery parameters on the
plugin dispatch path. This patch does not implement checkpoint commits there.

A new controlled probe showed `recover_expired_claim=0` was accepted by both
EvolveStepHandler and StartEvolveStepHandler, producing a delegation record.
Python equality treats zero as False, so the unsupported-option check silently
classified malformed numeric input as the default boolean. Baseline: two failed
negative tests, eighteen passing existing tests.

Compare both exact type and value against each option's default. Omitted and
correctly typed defaults retain existing delegation; malformed values fail
before work is recorded. Twelve new handler cases cover zero, float zero, null,
empty string/list/object. No provider call, policy change or plugin activation.

Focused source selection: 39 passed; changed source/tests Ruff check/format pass.
This is handler-level evidence, not a native OpenCode host or V2 acceptance run.
The declared MCP schema already requires a boolean; this guard protects direct
or malformed handler inputs rather than expanding the schema.
Codex retains final judgment; fork-only draft, no upstream merge/release.
