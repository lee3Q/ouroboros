# #2294 finding 5: conditional rename-capability fallback

Fork-only candidate, not a complete artifact-lifecycle fix. No upstream merge, formal review, issue closure or release.

## Scope and provenance

Changes only Hermes artifact publication and runtime-activation sibling rename call sites, with their tests. The Codex artifacts/uninstall/prune paths and new shared ownership primitives are not changed.

The final supplied patch was authored and tested against b0cbf991981ea1dcf45e2c86471b8908e9f0f0a4 (local commit 35e18e46719292eefb6a1ef090d6ed914a247a08). This fork candidate applies those bytes to c72d0b2d73ee5786f5abf0a56371bb9f096c00c6 and was independently tested there.

## Behavior

Missing or unsupported no-replace rename primitives use the existing Codex-style capability-degradation contract: files publish using no-follow hard links; directories reserve the destination and consume the reservation using rename. Occupied destinations are not intentionally overwritten. Reservation cleanup compares live descriptor and pathname identities. Other errors still raise. Darwin runtime activation checks and calls the same renameatx_np function, with missing/present/EINVAL controls.

## Validation and corrections

Independent c72 test environment: Python 3.14.9, PATH starts with the test environment, PYTHONPATH=src. tests/unit/cli/test_runtime_activation_rename_degradation.py and tests/unit/hermes/test_artifacts.py: 74 passed. Ruff check and format passed on all four changed Python files. The author's separate Python 3.12.15 / Ruff 0.17.1 result was also 74 passed, not an additional unique-test total.

Earlier candidates had a wrong Darwin-symbol check and missing blank lines. Both were caught during cross-check and repaired in the transmitted final patch. Prior format-pass claims do not describe those earlier bytes.

## Limits

This is not a universal atomic rename guarantee. File link publication followed by unlink is not one atomic move, and an unlink failure can leave both names. Directory reservation pathname-replacement races are not fully excluded when the native no-replace primitive is unavailable. Unsupported or network-filesystem behavior, including NFS, has not been validated on a real deployment. No actual user worktree or installed artifact was changed during tests. Other #2294 findings and automatic worktree cleanup are out of scope and unresolved.
