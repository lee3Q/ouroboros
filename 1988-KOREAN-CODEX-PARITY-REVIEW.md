# #1988: Korean Codex HTTP troubleshooting parity (bounded draft)

Base: df1ecbfbbdd6622ecaafc72a0797170963a08079.

All twelve runtime guides named by the original Korean-guide tracking issue now
have Korean files. This is not an audit of their complete semantic parity. One
specific remaining gap is that codex.ko.md lacks the existing English Codex
blank-console troubleshooting section and the incoming HTTP guidance link.

Translate that existing section, preserving its read-only PowerShell example
byte-for-byte. Keep the distinctions between operator startup and MCP workers,
listener presence and actual MCP health, and restarting a known server versus
indiscriminately killing a process tree containing durable jobs. No startup,
service or hidden-console implementation is added.

Validation: compare the added PowerShell block with current English source;
check the Korean heading/incoming anchor and existing local link targets; inspect
the rendered Korean section after publication. The original #2693 request for
Windows PowerShell 5.1 and PowerShell 7 execution is NOT fulfilled by source
comparison or rendering. No native Windows validation was performed here.

This is a partial documentation-parity draft for #1988, not full resolution of
#1988 or #2693 and not a translation of the newer OMP runtime guide. No broader
runtime/install behavior changes. Fork only; Codex final judgment. No upstream
merge, formal review or release.
