"""#2658 advisory characterization only: no provider or entitlement claims."""

import pytest

from ouroboros.orchestrator.adapter import ParamSupport
from ouroboros.orchestrator.codex_mcp_runtime import build_codex_mcp_worker_runtime
from ouroboros.orchestrator.model_routing import ModelRouter, decide_model


def _router(model: str) -> ModelRouter:
    return ModelRouter(
        tier_models={"standard": model},
        runtime_backend="codex_mcp",
        child_tier="frugal",
        base_tier="standard",
        escalation_retry_threshold=2,
    )


@pytest.mark.parametrize("support", list(ParamSupport))
def test_absent_router_is_none_not_advised(support: ParamSupport) -> None:
    decision = decide_model(support, router=None, is_decomposed_child=False)
    assert (decision.tier, decision.model, decision.mode) == (None, None, "none")
    assert not decision.is_enforced


@pytest.mark.parametrize("model", ["", "default", "auto", "current", " DEFAULT ", " Auto "])
def test_native_sentinel_model_is_advised_not_enforced(model: str) -> None:
    decision = decide_model(ParamSupport.NATIVE, router=_router(model), is_decomposed_child=False)
    assert decision.mode == "advised"
    assert not decision.is_enforced


@pytest.mark.parametrize("retry", [0, 1, 2, 3])
def test_codex_mcp_declares_ignored_and_never_claims_enforcement(retry: int) -> None:
    # Construction only. No subprocess is started and no provider is called.
    runtime = build_codex_mcp_worker_runtime()
    support = runtime.capabilities.model_override_support
    assert support is ParamSupport.IGNORED
    decision = decide_model(
        support, router=_router("fixture-model"), is_decomposed_child=False, retry_attempt=retry
    )
    assert decision.mode == "advised"
    assert not decision.is_enforced
