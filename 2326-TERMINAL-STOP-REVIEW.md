# #2326: retry interrupted terminal-session cleanup (bounded draft)

Base: 5b5f51597c1cb866058217f753525a76324ab2a1.

Main already binds termination controls, stops terminal broker sessions, shields
final cleanup and sanitizes child environment. This draft addresses one remaining
terminal-stop cancellation window, not the entire original leak report.

The terminal path set session_stopped=true before awaiting stop_session. If the
consumer task was cancelled while the stop awaited the broker, the existing
shielded finally skipped stop because the flag falsely said it had completed.
A new asyncio test reproduces this against main (one fail, twelve pass).

Set the flag only after stop_session returns. The existing shielded finally now
makes one bounded retry for cancellation or a GjcCoordinatorError on that first
stop. A successful acknowledged terminal stop remains one call; resumable
question/coordinator-error paths retain their existing policy. A second test
checks persistent stop errors cause exactly two attempts and still close the
connection, rather than an unbounded retry loop.

Validation: GJC runtime/client/LLM adapter selection24 pass,1 skipped; Ruff check
and format pass for both changed Python files. No live broker, worker process
tree or nested MCP server test was performed. Persistent broker failures still
cannot establish that the session was reclaimed, and this change does not add
a durable cleanup receipt or reaper. A terminal task result is not proof of
resource cleanup. No claim of full #2326 acceptance.

Fork only, Codex final judgment. No upstream merge, formal review or release.
