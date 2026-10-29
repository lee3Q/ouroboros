# #1861 issue reference audit draft

Base: Q00/ouroboros 71506032e48a36d10a392fd893963a7b41e854f6.
Issue: https://github.com/Q00/ouroboros/issues/1861

Explicit invocation only: `GH_TOKEN=<read token supplied locally> python scripts/report-merged-issue-references.py --repo Q00/ouroboros`. Never paste tokens into review or chat.

Uses GraphQL read queries, not mutations. Cursor-pages open issues, visible direct cross-reference/connected events, and closing PR references including closed PRs. Same-repo PRs only. A candidate needs >=1 reference and every PR MERGED/non-draft with mergedAt. Evidence includes plain/closing/connected kind. Missing source/repository, changed issue state, inconsistent PRs, errors, missing token or invalid pagination return indeterminate/nonzero, not empty success. Human must inspect acceptance criteria; historical references, edited mentions and reopened issues are not completion evidence. This is a read-over-time report, not an atomic snapshot.

Argon feedback caught a real REST/GraphQL field mismatch in the earlier local-only draft, so that version was replaced rather than published as valid. GraphQL fields and query fragments were checked against observed schema https://raw.githubusercontent.com/octokit/graphql-schema/master/schema.graphql . All3 queries have zero query-validation errors against it; the downloaded whole schema needs assume_valid because unrelated duplicate/deprecated-interface definitions fail graphql-core schema checks. This is static query checking, NOT live authenticated execution.

Validation:11 deterministic tests pass, Ruff lint/format pass, Linux Python3.14.9. Tests cover pagination of all3 connections, incomplete sources, nonmerged/draft/foreign refs, repeated-read idempotence, bounded request timeout, retry, read-query-only transport, GraphQL errors and absent credentials.

Live limitation: the abandoned public REST probe stopped HTTP403 at /pulls/2592 and emitted indeterminate. No authenticated GraphQL run performed, no token retrieved, no full successful repository audit claimed. No workflow, schedule, issue/comment/label/disposition mutation. The script is a fork-only proposal for Codex adoption/revision/rejection, not merge approval.
