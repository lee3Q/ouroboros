# #2231 local ambiguity-gate summary draft

Base: Q00/ouroboros 71506032e48a36d10a392fd893963a7b41e854f6.
Issue: https://github.com/Q00/ouroboros/issues/2231

`SeedMetadata.gate_forced` is already implemented on this base. This draft adds the missing read-only local summary, not a second marker or a telemetry change.

Usage: `ouroboros status ambiguity-gate --seed-dir .ouroboros/seeds`

It reads flat YAML/JSON Seed metadata, counts unique seed IDs, keeps historical missing/invalid marker and conflicting copies unknown, and computes forced / (forced + gated). Unknowns and unreadable files do not become successful gate checks. No current threshold inference, telemetry or mutation. Nested Seed folders are not included; the command names its flat-file scope. Use the directory containing the actual Seed files.

Focused validation: 557 passed across new CLI tests, existing status, core Seed and Seed generator tests on Linux Python 3.14.9. Ruff lint and format passed after formatting. No full CI or real user project run claimed.

Codex should decide whether this flat-directory summary is the smallest useful local first slice or whether canonical event-store/project ownership must replace it. Challenge duplicates/conflicts, historical denominator and file failures. This draft does not authorize upstream posting, issue closure, formal review, merge or release.

Argon feedback obtained, not adoption approval: conflict-latch claim was self-retracted and contradicts the explicit three-copy test. Added unique-ID total and provenance coverage; symlinks are counted unreadable rather than followed, stat/read errors handled per file. Invalid marker values intentionally remain unknown rather than successful gates; non-Seed YAML/JSON count unreadable documents, not corrupt Seed claims. No reason/verbose breakdown yet. Threshold inference and telemetry remain absent.
