# #2310: durable completed QA receipts (bounded draft)

Base: df1ecbfbbdd6622ecaafc72a0797170963a08079.

Main already validates threshold/history and derives the verdict from score.
The remaining non-plugin successful QA path returned a generated qa_session_id
without recording it. A real SQLite close/reopen test reproduced the reported
Session not found result after successful QA (one failing baseline test).

With an injected EventStore, successful non-plugin QA now appends a minimal
qa.evaluation.completed receipt in the separate qa aggregate. It stores only
iteration, score, score-derived verdict/action, threshold and passed. It does
not persist the artifact, reference, prompt, quality bar, model reasoning or
suggestions. An append failure returns an error rather than claiming durable
success. Without a store the existing verdict remains available and explicitly
reports receipt_persisted=false.

Unified session_status first preserves the existing orchestrator reconstruction
path. If that fails it can return the most recent completed QA receipt, labelled
session_kind=qa and status=evaluated. This does not fabricate a Seed execution,
progress, acceptance, or a claim that the model actually executed probes. QA can
finish with passed=false. Multiple evaluations remain separate append-only
receipts; the latest persisted receipt is shown, not a made-up running state.

Not covered: in-flight or failed QA persistence, host serialization coercion,
long host timeouts, plugin child-result ingestion, or retroactive restoration of
missing historical receipts. Plugin handoff is not completion. Standalone
handlers without an injected store still do not gain a new implicit database.
This partial source fix does not close the entire umbrella issue.

New tests cover SQLite reopen/status, no-store explicit false, persistence
failure, repeated evaluations, missing IDs, private-text exclusion and absence
of fabricated orchestrator session events. Existing QA/parser/schema and MCP
adapter selections are also run. Fork only; Codex final judgment, no upstream
merge, formal review or release.

## Follow-up: direct/plugin input boundary

Before prompt construction, logging, provider selection or plugin handoff,
reject non-string/non-empty quality_bar, unsupported artifact_type, non-string
optional reference/seed_content, and supplied empty/non-string qa_session_id.
No coercion is introduced. Valid strings are preserved verbatim and all six
advertised artifact types remain valid. Empty artifact/reference/seed_content
remain supported. Malformed session IDs cannot become aggregate identifiers.
24 malformed direct/plugin cases reproduced 22 failures before this change;
6 valid plugin compatibility cases preserve exact values. These checks protect
handler callers that bypass external schema validation. They do not relax host
inputSchema validation or accept serialized numeric/history strings.
