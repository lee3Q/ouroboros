# #2535: reject background receipts with zero exit status (bounded follow-up)

Base: df1ecbfbbdd6622ecaafc72a0797170963a08079.

Current main already projects OMP tool start/end events and enables no-session
constructor calls. This draft does not reimplement those changes or claim a
native OMP end-to-end run.

## Reproduced gap

A controlled OMP Bash completion containing `details.exitCode: 0`,
`details.async.state: running` and success-looking pytest output was admitted
by the actual atomic evidence verifier as completed test proof. The added
negative case failed on unmodified main (1 failed, 21 passed). A background
receipt must not prove completed execution, regardless of its output.

## Change

Mark any result containing a `details.async` key as invalid completion evidence,
including malformed async values and a purported completed state. This is the
same conservative boundary already used to withhold inferred zero exit status.
Preserve the raw reported exit status and result for diagnosis, but attach the
existing invalid-evidence bits that the verifier and journal gate already read.
No runner parsing, retry policy, provider settings or session lifecycle change.

Seven new negative cases cover running/completed objects, null, false, string,
empty object and list. Each remains rejected by the atomic verifier and the
journal success gate despite an explicit zero exit and pytest pass text.
Existing synchronous success, failures, interleaving and constructor tests stay
in the selection. Local focused selection: 82 passed; changed files Ruff pass.

## Limits

This is controlled stream evidence, not a recovered native incident or live OMP
background lifecycle test. It does not introduce asynchronous terminal receipt
support. Native OMP sessions and full Seed execution remain untested here.
Codex retains final judgment. Fork draft only, no upstream review or merge.
