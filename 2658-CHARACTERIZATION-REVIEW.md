# #2658 model-routing characterization, not a runtime fix

Base: c72d0b2d73ee5786f5abf0a56371bb9f096c00c6.

The only implementation artifact here is a new test file with 13 cases. It records current behavior: no router when absent, advice without enforcing a runtime-native model change, and Codex MCP routing declared IGNORED across retry values 0 through 3. Tests construct the actual runtime classes but do not launch a provider subprocess.

Independent clean-base verification: the selected existing 90 tests and new 13 tests passed, 103 total. Ruff check and format passed for the new file. This is not evidence of a native provider model change, subprocess dispatch, updated provider model inventory, or resolution of #2658.

Argon review of this exact candidate has not run. The user removed the Gemini review requirement for Ouroboros on October 29, 2026. This is a scope decision, not completed Gemini review or approval. Final Codex judgment remains with the user. Do not merge upstream, close the issue or release from this candidate.
