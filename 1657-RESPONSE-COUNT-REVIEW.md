# #1657: exact submitted-response character evidence (partial draft)

Base: c72d0b2d73ee5786f5abf0a56371bb9f096c00c6.

This patch adds `response_chars` at the existing `interview.response.recorded`
event boundary. The MCP answer path passes the complete `answer` to that
factory before its preview is truncated. Previously two answers sharing their
first 200 code points could not be distinguished by length in the event store.
The existing 200-character text preview remains unchanged.

The count uses Python Unicode code points, including whitespace and combining
marks. It is submitted text, not keystrokes, grapheme clusters, proof of human
authorship, or user decisions. A host can supply generated text at this boundary.
No additional answer text, credentials, or environment values are stored.

## Limits

This does not complete #1657. It does not define decision/approval semantics,
count host-visible turns, instrument CLI-only paths, correlate the first Seed,
or supply the three persona golden baselines and approved regression tolerance.
Old events lack the count; a truncated preview must never be used as an exact
historical count. Existing timing exports intentionally remain unchanged.
No telemetry is added and no interview policy or authority is changed.

## Verification

Eight new focused event tests cover empty, short, boundary, long, Korean/emoji/
combining-mark and whitespace inputs, preview privacy and distinct long counts.
The existing handler call site was inspected; no live host or first-Seed E2E
acceptance is claimed. See the accompanying execution report for suite results.
