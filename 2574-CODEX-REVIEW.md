# #2574: explicit src-layout import-origin diagnostic

Draft only. No upstream merge, review, issue closure or release.

## Scope

The current controller already proves CLI files from the checkout before switching to a case-file working directory. The remaining src-layout limitation is real, but adding `src` to `sys.path` would not prove what the selected interpreter imports.

This candidate addresses the issue's explicit alternative, "or is reported with a specific reason": when a top-level target has no direct checkout module/package and a complete regular source target exists under `src/`, return `unprovable` with `checkout_src_module_requires_import_origin_proof`, rather than reporting the module absent. The source candidate is checked with the existing no-follow checkout-file proof. A namespace, extension-shadowed, absent or linked candidate does not receive this diagnostic.

No arbitrary package is imported for discovery. No interpreter search path, harness execution or tier-A admission rule changes. A direct root module retains priority. A src-only oracle remains tier U and cannot pass as a proven target.

## Validation

Base: c72d0b2d73ee5786f5abf0a56371bb9f096c00c6. Python 3.14.9; PATH starts with the test environment; PYTHONPATH=src.

`tests/unit/boundary/test_cli_launch.py`, `test_oracle_run.py`, and `test_built_call_oracle.py`: 111 passed, 3 skipped. Ruff check and format passed for both changed Python files. Nine new parameterized cases cover src package/module/single-file diagnosis, missing/namespace/external symlink/extension shadow controls, root precedence, and no tier-A promotion. Existing target swap regressions were included.

## Still open

This does not resolve the selected interpreter's editable-install/import origin or enable execution of src-layout modules. It is a bounded diagnostic fix, not complete #2574 implementation or proof of the reported pytest benchmark case. Native Windows and remote CI were not run. Automatic `src` path insertion is deliberately excluded.
