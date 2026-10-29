# PR #2196: verification working-directory draft

Fork-only review candidate. No upstream merge, review, issue closure or release was performed. This is not a whole-suite green or merge-ready claim.

## Source and scope

- Upstream PR: https://github.com/Q00/ouroboros/pull/2196
- Upstream PR head reviewed: `6c7bc5c71645724218d5310f787cd2bd854f8d35`.
- Reconstructed integration originally used main `70293b5831437a43abe537c8d1538d09e14beccb`.
- Actual fork publication base: `90cde708732c76e41e7af6e15786bb33c265afdf`. Its four unrelated changes were preserved, not overwritten.
- Published source before the final fixture lint correction: `70facfe8b87d4c605e21201236f51eda10e9e448`.
- The 22 source, test and documentation files were fetched back and compared byte-for-byte with the intended candidate. Temporary upload filenames were removed.

This carries the full reconstructed PR, not merely an additive fixup. It adds the acceptance-criterion working-directory contract, normalizes and checks workspace-relative directories, routes verification commands and base signals to the selected directory, extends the execution capsule's scoped artifact handling, and adds corresponding source documentation and tests. Existing default behavior remains subject to the tests and review boundaries below.

## Additional fixture correction

The Windows workspace-capacity test previously passed a Windows-looking path through the host's `realpath`. On Linux its result depended on the checkout directory length. Both Python 3.12 and 3.14 reproduced that short/long-path difference. It was not established as a Python-version defect.

The fixture now supplies a fixed Windows absolute path to the capacity validator. This is test-only. The unused lambda argument is named `_workspace` to satisfy Ruff. Production capacity behavior was not changed by this correction.

## Verification at 2026-10-29 KST

Independent local run: Linux, Python 3.14.9, existing dependency environment, `PYTHONPATH=src`.

The exact fetched published source at `70facfe8` ran the following selection: **1539 passed, 2 failed, 1 skipped**.

```sh
python -m pytest \
  tests/unit/orchestrator/test_verify_cwd.py \
  tests/unit/orchestrator/test_parallel_executor.py \
  tests/unit/orchestrator/test_parallel_executor_verify_by_default.py \
  tests/unit/orchestrator/test_ac_execution_capsule.py \
  tests/unit/orchestrator/test_verify_base_signal.py \
  tests/unit/orchestrator/test_verify_command_runner.py \
  tests/unit/auto/test_execution_acceptance.py \
  tests/unit/bigbang/test_seed_generator.py \
  tests/unit/core/test_seed.py \
  tests/unit/evaluation/test_semantic.py -q
```

After the `_workspace` lint-only fixture correction, the entire capsule file ran again: **62 passed**. Ruff check passed for all changed Python files. This was not a complete rerun of the 1542-test selection after that one-line correction.

Remaining failed nodes:

1. `tests/unit/orchestrator/test_parallel_executor.py::test_capture_rejects_intermediate_workspace_ancestor_swap`
2. `tests/unit/orchestrator/test_parallel_executor.py::TestParallelACExecutor::test_fat_harness_exit_code_only_test_output_is_settled_by_harness_reexecution[True]`

Both failed on the older exact `70293b58` baseline control. On the actual `90cde708` publication baseline, the fat-harness node failed again but the ancestor-swap node passed. The candidate's ancestor-swap failure therefore cannot be dismissed as a proven baseline-only failure. Its cause and intermittency remain unresolved. A same-node baseline failure also does not by itself prove equal causes or rule out other regressions.

## Review boundaries

- No Windows execution, fresh wheel installation, live provider run, remote CI, or end-to-end workflow was completed here.
- This draft was not combined with every other open PR. In particular, shared executor changes need explicit integration against the chosen final heads.
- Earlier reported conflict failures from an incorrectly resolved local tree were withdrawn and are not evidence against this corrected tree.
- No final independent review of this exact source was completed. The user's Codex review retains final judgment.
- Investigate the ancestor-swap failure and fat-harness failure before treating this as merge-ready. Do not close unrelated issues based on this scoped draft.
