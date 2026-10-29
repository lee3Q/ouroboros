# #2305 fork-only draft for Codex judgment

Status: unapproved proposal, NOT an upstream PR, NOT a claim that native Pi lost-wakeup is fixed. No release work.

Base source: Q00/ouroboros commit 71506032e48a36d10a392fd893963a7b41e854f6.
Issue: https://github.com/Q00/ouroboros/issues/2305
Related merged cleanup only: https://github.com/Q00/ouroboros/pull/2705

## Proposed contract
The leaf dispatcher should retain its own stall deadline when a cooperative provider async generator keeps an AnyIO shield scope across an await/yield. Provider iteration runs in an owned task. Explicit per-message acknowledgement prevents advancing the provider until the consumer has processed the previous message, preserving tool-call filesystem lease ordering. Message/state/event/evidence processing stays in the consumer task. Consumer failure and external cancellation propagate after provider cleanup. Provider exceptions remain failures, not synthesized success.

Non-goals: native lost-wakeup root-cause claim; forcibly stopping code that swallows cancellation; process-tree policy; verifier acceptance changes; release, upstream issue mutation, formal reviews or merge.

## Actual changes
The actual changed source and ten regression tests are committed on `draft/2305-runtime-stream`, branched from the pinned upstream base. The fork's default main branch is unchanged.

```sh
git clone --branch draft/2305-runtime-stream https://github.com/lee3Q/ouroboros.git ouroboros-review
cd ouroboros-review
uv sync --group dev --extra mcp
uv run pytest -q tests/unit/orchestrator/test_runtime_stream.py tests/unit/orchestrator/test_command_artifact_provenance.py --no-cov
```

## Evidence and limits (Linux, Python 3.14.9)
- New exact dispatcher shield/deadline test fails unchanged main (outer TimeoutError), passes candidate.
- Ten new tests passed three consecutive runs.
- New tests + command artifact provenance: 520 passed (510 existing +10 new).
- Related runtime/dispatcher/authority/routing/Synapse selection: 811 passed, 1 deselected.
- Provenance plus evidence directory: 1346 passed, 3 skipped.
- Targeted MyPy (2 changed source files), Ruff lint/format, module-size baseline HEAD, git diff --check passed.
- The deselected existing fingerprint/touch test independently fails unchanged main; another wider run stopped after 3045 passed/3 skipped on Codex sibling-churn failure, also reproduced unchanged main. Full suite not green or complete. No CI run claimed. The draft branch uses the pinned upstream base, not the older fork default main.
- Native Pi/OMP authenticated run and original native incident not reproduced. No claims about user's Mac environment.

## Important independent feedback
San found a real defect in v2 (and same lookahead remained v3): bounded queue alone let provider side effects execute before consumer established a Bash lease. Existing provenance suite baseline510 pass vs v2 47 fail. V4 adds explicit processed acknowledgement; author's rerun510+10 pass. San's v4 independent verdict is pending at handoff preparation time, not presumed approved.
Argon v1/v2 challenged cancellation and cleanup. Confirmed consumer-error masking fixed; repeated native cancellation tested and joined. Its scope-stack-in-ContextVar assertion did not match installed AnyIO backend (_task_states keyed by task); nested scope tests passed. V4 feedback received: lockstep handoff normal behavior supported; cancellation edge cases remain suggestions to verify, not approval.

## Request to Codex
Please inspect this fork-only proposal and changed source/tests, rerun the exact tests on the pinned base, challenge producer/consumer ordering, task-local authority and cancellation/cleanup, and decide whether this is a useful bounded fix for #2305. Reject or revise it if the original user-visible contract is not served. Do not infer native-root-cause resolution or full green CI from focused tests. Return the final decision and remaining checks to Sang Gyu. No upstream posting, issue closure, formal review, merge, or release is authorized by this review request.

Patch SHA-256: `884cbb9c22092a80da35cc77adefbc0ac3b90be6a3250ead8161188ac49448e4`.
