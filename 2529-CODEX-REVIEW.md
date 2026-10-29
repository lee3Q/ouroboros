# #2529: cleanup compatibility across OpenCode plugin generations

Fork-only partial draft. No upstream merge, review, issue closure or release.

## Actual change

Recognize the V1 `plugins/ouroboros-bridge/ouroboros-bridge.ts` entry, V2 directory registration, and manually migrated `index.ts` / `index.js` entries. Match the exact directory tail, including Windows separators, without taking ownership of other plugins.

Uninstall, its target preview, and switching to subprocess mode now remove matching bridge registrations from both `plugin` and `plugins` arrays. Unrelated plugins, malformed non-list keys, and other config values are preserved. Config writes use the existing atomic-write helper. Dry runs preserve bytes and plugin files; no-match cleanup does not rewrite the file or strip comments. Changed JSONC still warns once before the write.

## Validation

Base c72d0b2d73ee5786f5abf0a56371bb9f096c00c6. Python 3.14.9; PATH starts with the test environment; PYTHONPATH=src.

Focused bridge-generation, OpenCode config/version, setup and uninstall suites: 560 passed, 4 skipped. The new generation matrix has 29 cases, including public uninstall dry-run preview, both config suffixes, both cleanup paths, mixed arrays, malformed keys, atomic-write failure, negative identity matches and byte-preserving no-op behavior. Changed Python Ruff check/format pass.

## Still open

This does not port the V1 bridge to V2 `setup` / effect APIs, enable V2 child Task dispatch, or prove `delegated_to_plugin` on a real host. Existing detected-V2 setup rejection and subprocess fallback remain unchanged. Real OpenCode 2.x and native Windows host runs were not performed. Recognition of V2 directory entries is cleanup support, not evidence that the V1 bridge can load on V2.

The V2 contract was checked against the official migration/server-plugin documentation and the published @opencode/plugin 2.2.0 types. This patch deliberately does not add a fake setup export or silently register an incompatible plugin.

Sources: https://opencode.ai/v2/docs/build/plugins/migrate-v1/ and https://opencode.ai/v2/docs/build/plugins/server/ .
