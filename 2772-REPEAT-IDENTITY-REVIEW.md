# #2772: exact integer repeat identities (bounded follow-up)

Base: df1ecbfbbdd6622ecaafc72a0797170963a08079.

The existing examples package contains outcome records, disagreement/card logic
and probe wrappers. This draft does not add candidate execution, requester picks,
held-out acceptance or requester memory, and does not activate an auto path.

OutcomeRecord rejected boolean repeat IDs but accepted floating-point 0.0/1.0
because equality against (0, 1) aliases them to integer repeat identities. A
malformed repeat could enter the disagreement index as if it identified one of
the required integer execution repeats. Two new negative tests failed on main
(2 failed, 21 passed in the record selection).

Require exact int type before checking the closed repeat set. Existing valid
integer repeat IDs remain unchanged. This is input-boundary hardening, not proof
that the two required executions really occurred or that outcomes are authentic.
Both malformed float aliases are rejected; the existing examples suite remains
in the verification selection. No expected values or user intent are invented.
Fork-only draft; Codex final judgment, no upstream merge or release.
