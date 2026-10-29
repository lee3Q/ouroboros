"""Malformed direct/plugin QA input never reaches model or dispatch."""

from unittest.mock import AsyncMock, patch

import pytest

from ouroboros.mcp.tools.qa import QAHandler


@pytest.mark.parametrize(
    "field,value",
    [
        ("quality_bar", True),
        ("quality_bar", {}),
        ("quality_bar", ["works"]),
        ("artifact_type", []),
        ("artifact_type", None),
        ("artifact_type", "unknown"),
        ("reference", {}),
        ("reference", False),
        ("seed_content", []),
        ("qa_session_id", {}),
        ("qa_session_id", True),
        ("qa_session_id", ""),
    ],
)
@pytest.mark.parametrize("backend", ["claude", "opencode"])
async def test_malformed_input_stops_before_prompt_or_dispatch(field, value, backend):
    adapter = AsyncMock()
    handler = QAHandler(llm_adapter=adapter, agent_runtime_backend=backend, opencode_mode="plugin")
    with (
        patch("ouroboros.mcp.tools.qa.build_qa_subagent") as build,
        patch(
            "ouroboros.mcp.tools.qa.dispatch_plugin_terminal", new_callable=AsyncMock
        ) as dispatch,
    ):
        result = await handler.handle({"artifact": "x", "quality_bar": "works", field: value})
    assert result.is_err
    assert field in str(result.error)
    build.assert_not_called()
    dispatch.assert_not_awaited()
    adapter.complete.assert_not_awaited()


@pytest.mark.parametrize(
    "artifact_type", ["code", "api_response", "document", "screenshot", "test_output", "custom"]
)
async def test_valid_plugin_input_keeps_exact_values(artifact_type):
    handler = QAHandler(agent_runtime_backend="opencode", opencode_mode="plugin")
    from ouroboros.core.types import Result

    args = {
        "artifact": "",
        "quality_bar": " works ",
        "artifact_type": artifact_type,
        "reference": "",
        "seed_content": "",
        "qa_session_id": "qa-explicit",
    }
    with (
        patch("ouroboros.mcp.tools.qa.build_qa_subagent") as build,
        patch(
            "ouroboros.mcp.tools.qa.dispatch_plugin_terminal", new_callable=AsyncMock
        ) as dispatch,
    ):
        dispatch.return_value = Result.ok("delegated")
        result = await handler.handle(args)
    assert result.is_ok
    assert build.call_args.kwargs["quality_bar"] == " works "
    assert build.call_args.kwargs["artifact_type"] == artifact_type
    assert build.call_args.kwargs["qa_session_id"] == "qa-explicit"
    dispatch.assert_awaited_once()
