# Console interview: experience preview and reviewed Seed

New Console Interview previews use a completion-only LiteLLM provider to propose a
concrete experience before implementation. Configure a supported provider and
model in the Console; the provider may be a local OpenAI-compatible gateway.
The execution agent is selected separately, defaulting to the configured Execute
stage. It is saved with the chat so a later settings change does not silently
switch its executor. No CLI fallback is used for preview generation.

The model chooses `ask`, `preview`, or `ready` from requester evidence and
consequential unresolved decisions. There is no ambiguity threshold or minimum
question count. A small task may need only one scene. Each scene describes an
action, visible result and failure alternative. The proposal displays its goal,
observable success criteria, constraints, assumptions and verbatim user evidence.
A `ready` judgment requires a nonempty goal and criteria, a concrete scene, and
no required decisions. These are structural checks, not proof of understanding
or a claim that the model found every unresolved decision.

Corrections trigger a fresh judgment. All user messages and the last generated
preview reach the model; full chat history remains on disk. Invalid JSON or
unsupported evidence quotes fail visibly. A new message retries a failed or
interrupted preview. An oversized requester history asks for a new chat while
preserving the original. Rendered proposals are text, not executable markup.

## From review to execution

1. Review or correct the proposed goal, success criteria, constraints and scenes.
2. Choose **Confirm this scope and create Seed**. The server copies the displayed
   goal, criteria and constraints without a second synthesis. Assumptions remain
   nonbinding. A content revision binds the proposal to this chat and requester
   history; stale revisions and `force` cannot bypass missing decisions.
3. Choose the separate execution action when ready. It validates the current
   reviewed revision and persisted Seed digest before using the selected agent.
   Model readiness and Seed creation do not start execution.

A correction clears the active Seed and approval while retaining their history.
Scope cannot change while a previous execution's termination is unknown. When
an existing execution is known, reconnecting follows it instead of starting a
replacement. A confirmed failed terminal job can be explicitly retried with a
new attempt key. The normal run handler owns worktree creation and execution. The current Console
folder-preparation flow still requires explicit `prepare_git` permission when a
folder lacks a repository or first commit. Missing execution CLIs are refused
before creating a preview chat. Legacy repository-assisted answers and their
correction history remain on the existing interview path.

Dispatch intent is saved before calling the starter. If the process stops after
acceptance but before both execution/job handles are saved, the Console cannot
prove whether dispatch succeeded. It blocks another run and scope changes, and
directs the operator to Runs for manual investigation. This boundary does not
promise automatic receipt recovery or durable backend deduplication. Cancelled
and interrupted jobs terminate the Console follower even when no execution-side
terminal event was emitted.

Seeds use `generation_mode: reviewed_console_preview` and
`ambiguity_score: null`; no substitute numeric score is invented. The
`reviewed_preview` extra records revision, scenes and quoted evidence. This is
historical provenance, not transferable approval for an evolved child Seed.
The Console chat's current revision and Seed digest own its execution approval.

## Compatibility and limits

Previously saved ordinary interviews retain their legacy dispatch. API clients
can explicitly request `preview_first: false` for that compatibility path. An
explicit native CLI backend also retains the existing interview flow unless
preview is explicitly requested (which requires LiteLLM). New default-provider
Console interviews use preview; Auto, Ask, CLI, MCP and PM readiness
policies are not migrated by this change. Numeric Auto grading rejects an
unmeasured score unless an existing structural/degraded closure rule applies.
A generation-mode label alone does not bypass those gates.

The preview completion does not inspect a repository or call external tools.
User statements are evidence of intent, not proof that a capability exists.
The action endpoint uses the Console's existing token/authentication boundary;
a recorded review action is not proof of the identity or satisfaction of a
particular human. A full human usability study and deployment are outside this
implementation's verification. New strings are localized in Korean and English;
other catalogs currently use the English wording for these additions.

## Verification

Regression coverage includes evidence validation, one-scene tasks, missing
required decisions, failed/interrupted preview recovery, exact Seed roundtrip,
stale/cross-session revision rejection, correction invalidation, independent
execution dispatch, executor stage defaults, reconnect/retry handling and
nullable-score consumers. Frontend typecheck/build and Python targeted type and
lint checks accompany these tests.

Live testing uses an isolated Console and separate settings, an existing local
completion gateway, and a real browser. Test conversations and screenshots are
kept outside the source tree; they are agent-driven checks, not human approval.
A tiny independent Git fixture exercises reviewed Seed handoff without touching
an application repository. See the task verification report for exact outcomes
and versions; do not infer deployment from a local build.
