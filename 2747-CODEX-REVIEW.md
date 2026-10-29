# PR #2747: config-reference contract draft

Fork-only review candidate. No upstream merge, formal review, issue closure or release was performed. This is not a whole-repository green or merge-ready claim.

## Exact source

- Upstream PR: https://github.com/Q00/ouroboros/pull/2747
- PR head: `31d8e1e2a03257e8d905cb9fb4b9bbaf92d64ea2`.
- Actual publication base: `c72d0b2d73ee5786f5abf0a56371bb9f096c00c6`.
- Published five-file source before this handoff: `8c60d46b5deed8494fc7fa6e61fc37ca4ac766cd`.
- All five source/workflow/documentation files were fetched and compared byte-for-byte with the intended local integration. Upload staging filenames were repaired.

The draft carries the full PR: config-field effective-control annotations, the static config-reference contract checker, its tests and workflow integration. It does not make the documented inert fields active runtime controls. It also includes San's two-file Ruff formatting correction, with no semantic changes in that correction.

## Verification

Independent Linux Python 3.14.9 run, existing test environment, `PYTHONPATH=src`:

- `pytest tests/unit/scripts/test_check_config_reference_contract.py -q -k 'not standalone'`: **761 passed, 3 deselected**.
- Two separately selected cache tests, `test_standalone_validation_cache_reuses_identity_without_structural_work` and `test_standalone_validation_cache_rechecks_current_limits`: **2 passed**.
- `test_current_repository_passes_standalone_contract`: did not finish within a bounded 80-second run, exit 124. No pass/fail verdict. The PR's workflow already deselects this one node; this draft does not add that deselection.
- Exact CI-pinned Ruff **0.17.0**: `ruff check src/ tests/ scripts/check-config-reference-contract.py` passed; `ruff format --check` on the same selection passed with **1721 files already formatted**.

San independently reported the earlier PR/b0cb integration's 761 passing tests with three standalone-named tests omitted, and CI failure at formatting rather than rule checks. His earlier report of 689 lint errors was withdrawn as unsupported. It must not be retained as an actual result.

## Boundaries

The slow full-repository standalone contract check remains unverified, as do remote CI on this fork, Windows and all-PR combined integration. No result here establishes the whole #1998 issue resolved or changes the user's final Codex judgment. Existing and newly introduced inert configuration fields still require the requested contract-specific audit rather than a blanket fix claim.
