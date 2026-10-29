# Structured question batches: incomplete opt-in draft

Issues: https://github.com/Q00/ouroboros/issues/1651 , https://github.com/Q00/ouroboros/issues/1652 , https://github.com/Q00/ouroboros/issues/1653

Published base: b0cbf991981ea1dcf45e2c86471b8908e9f0f0a4. Source/test head before this handoff: ef757e8bc2bc2edc08bbf805eaa70c68730fcac1. This is not a claim that these issues are solved or merge-ready.

## Actual connected behavior

The existing ouroboros_interview MCP tool now exposes question_batch, batch_question_ids, batch_dependencies, batch_capacity and batch_id. The opt-in route uses the real InterviewEngine and LLMAdapter boundary: one model call for generation, pending JSON persistence, zero-call resume, all-answer validation, deep-copy recording through record_response, and compare-and-save under the existing file lock. Batch answers require the current batch_id. Invalid answer attempts persist up to three; the pending batch is then retained but no further answer is accepted. Ordinary handler/engine paths reject pending batches rather than advancing or completing them. This route never scores ambiguity or marks Seed-ready.

Choices carry source labels and recommendations. Generated user/document claims are rejected unless exact choice text/source/id is supplied by a separate trusted caller boundary; the MCP route supplies none, so its generated choices remain generated. Selected text is a user decision while original option_sources remain recorded. Empty multi-select is an explicit selected=[] record, not an empty answer. Numeric/letter choices, comma selections, numbered text, and explicit other: free text are supported. Selection order is canonical.

## Limits and review blockers

- Independence is caller_asserted_not_verified. Explicit empty dependency arrays are required; known dependencies are rejected before generation. This does not establish semantic independence or implement an automatic question planner.
- Native payload is runtime-neutral data only. No live host widget adapter was run or implemented. Capacity splits presentation only; all numbered answers must be submitted together. Chunk-by-chunk answer collection is not implemented.
- Plugin-dispatch mode rejects the opt-in route. Existing single-question mode remains the default.
- Reference/calibration inputs and unresolved reference/terminology state are rejected on this route. This deliberately avoids silently bypassing their ordinary path, but it is not integrated novice-language calibration support.
- No three-persona golden transcript or Seed-output equivalence result exists. Existing Seed scoring/closure is not changed.
- A compare-and-save protects this route from changed state before its own write. This is not a global transaction retrofit for every legacy writer; broader concurrent ordinary-write interactions remain a review concern.
- Model generation is bounded to 32k response characters but the prompt uses persisted state directly. Native CLI prompt-budget integration needs review for long histories.
- No live provider, Windows, installed-wheel or hosted CI result is claimed.

## Evidence

On exact fetched published source head ef757e8, all six source/test files matched local intended bytes. The diff from b0cb contains only those six files: 1032 additions. Focused command:

    PYTHONPATH=src python -m pytest tests/unit/bigbang/test_question_batch.py tests/unit/bigbang/test_interview.py tests/unit/mcp/tools/test_interview*.py -q

271 passed on the actual published base/source. Ruff check passed on all six files. New tests cover generation count, dependency rejection, text/native validation, capacity content preservation, persisted resume, failed partial answer atomicity, stale batch identity, stale compare-and-save and two concurrent duplicate answers committing once.

Earlier local base715 source also passed271. V2 source (before six provenance-only lines) combined with PR2702 head f09998f21007c80a47fdb829a63732c75867156e passed300 selected tests after resolving one ask_next_question context conflict by placing the pending guard before the existing language_calibration branch. That is not a published-base or V3 combination result. San's independent PR1843/2702 comparison was static/application evidence, not an independent runtime rerun; only their two interview files were proven identical.

Argon design feedback raised interleaving, chunk-answer collection, source provenance and semantic independence risks. It was not a review of final exact source. Deep copy, pending guards, batch identity and compare-and-save have tests; the limits above remain unclosed. Codex must review the exact source and decide the remaining integration work, not infer whole-issue completion from test counts.

No upstream issue closing, formal review, merge or release was performed.
