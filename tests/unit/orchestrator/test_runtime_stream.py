"""Dispatcher/provider task ownership regressions for #2305."""

import asyncio
from contextvars import ContextVar
from types import SimpleNamespace

import anyio
import pytest

from ouroboros.orchestrator.adapter import AgentMessage
from ouroboros.orchestrator.leaf_dispatcher import LeafDispatcher, LeafDispatchState
from ouroboros.orchestrator.runtime_stream import isolated_runtime_stream


@pytest.mark.asyncio
async def test_provider_scope_cannot_shield_leaf_stall_deadline(monkeypatch):
    closed = asyncio.Event()

    class Runtime:
        working_directory = None

        async def execute_task(self, **kwargs):
            try:
                with anyio.CancelScope(shield=True):
                    await asyncio.Event().wait()
                if False:
                    yield
            finally:
                closed.set()

    monkeypatch.setattr("ouroboros.orchestrator.leaf_dispatcher.STALL_TIMEOUT_SECONDS", 0.02)
    executor = SimpleNamespace(
        _task_cwd=None, _adapter=Runtime(), _is_resumable_runtime_handle=lambda _: False
    )
    state = LeafDispatchState(messages=[], runtime_handle=None)
    await asyncio.wait_for(
        LeafDispatcher(executor).stream(
            state=state,
            prompt="test",
            tools=[],
            system_prompt="",
            execute_effort_kwargs={},
            runtime_identity=None,
            execution_context_id="e",
            session_id="s",
            ac_index=0,
            ac_content="test",
            is_sub_ac=False,
            parent_ac_index=None,
            sub_ac_index=None,
            node_identity=None,
            retry_attempt=0,
            semantic_ac_key="ac",
            label="AC",
            indent="",
            execution_counters=None,
        ),
        timeout=1,
    )
    assert state.stalled
    assert closed.is_set()


@pytest.mark.asyncio
async def test_order_backpressure_and_context_inheritance():
    marker = ContextVar("marker", default="outside")
    token = marker.set("dispatch")
    observed = []
    produced = []

    async def source():
        observed.append(marker.get())
        marker.set("provider")
        for index in range(10):
            produced.append(index)
            yield AgentMessage(type="assistant", content=str(index))

    try:
        async with isolated_runtime_stream(source()) as messages:
            await asyncio.sleep(0.02)
            assert len(produced) <= 2
            assert [m.content async for m in messages] == [str(i) for i in range(10)]
        assert observed == ["dispatch"]
        assert marker.get() == "dispatch"
    finally:
        marker.reset(token)


@pytest.mark.asyncio
async def test_queued_messages_precede_provider_error():
    error = ValueError("provider failed")

    async def source():
        yield AgentMessage(type="assistant", content="partial")
        raise error

    received = []
    with pytest.raises(ValueError) as caught:
        async with isolated_runtime_stream(source()) as messages:
            async for message in messages:
                received.append(message.content)
    assert caught.value is error
    assert received == ["partial"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_early_exit_or_external_cancel_closes_provider(cancel):
    closed = asyncio.Event()
    entered = asyncio.Event()

    async def source():
        try:
            yield AgentMessage(type="assistant", content="one")
            entered.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def consumer():
        async with isolated_runtime_stream(source()) as messages:
            async for _ in messages:
                if not cancel:
                    return

    task = asyncio.create_task(consumer())
    if cancel:
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await task
    assert closed.is_set()
    assert not [t for t in asyncio.all_tasks() if t.get_name() == "ouroboros-leaf-runtime-stream"]


@pytest.mark.asyncio
async def test_nested_provider_and_outer_consumer_scopes_are_independent():
    closed = asyncio.Event()

    async def source():
        try:
            with anyio.CancelScope():
                with anyio.CancelScope(shield=True):
                    await asyncio.Event().wait()
            if False:
                yield
        finally:
            await asyncio.sleep(0)
            closed.set()

    with anyio.move_on_after(0.02) as scope:
        async with isolated_runtime_stream(source()) as messages:
            async for _ in messages:
                pass
    assert scope.cancelled_caught
    assert closed.is_set()


@pytest.mark.asyncio
async def test_second_native_cancellation_does_not_interrupt_provider_cleanup():
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    closed = asyncio.Event()
    entered = asyncio.Event()

    async def source():
        try:
            entered.set()
            await asyncio.Event().wait()
            if False:
                yield
        finally:
            cleanup_started.set()
            await release_cleanup.wait()
            closed.set()

    async def consumer():
        async with isolated_runtime_stream(source()) as messages:
            async for _ in messages:
                pass

    task = asyncio.create_task(consumer())
    await entered.wait()
    task.cancel()
    await cleanup_started.wait()
    task.cancel()
    await asyncio.sleep(0)
    release_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)
    assert closed.is_set()


@pytest.mark.asyncio
async def test_expiring_provider_scope_during_backpressure_finishes_own_cleanup():
    closed = asyncio.Event()

    async def source():
        try:
            with anyio.move_on_after(0.02):
                try:
                    for i in range(10):
                        yield AgentMessage(type="assistant", content=str(i))
                finally:
                    with anyio.CancelScope(shield=True):
                        await asyncio.sleep(0)
                        closed.set()
        finally:
            closed.set()

    async with isolated_runtime_stream(source()) as messages:
        await asyncio.sleep(0.05)
        async for _ in messages:
            pass
    assert closed.is_set()


@pytest.mark.asyncio
async def test_provider_cannot_advance_before_consumer_finishes_message():
    advanced = False

    async def source():
        nonlocal advanced
        yield AgentMessage(type="tool", content="start")
        advanced = True
        yield AgentMessage(type="tool_result", content="done")

    async with isolated_runtime_stream(source()) as messages:
        async for message in messages:
            if message.type == "tool":
                await asyncio.sleep(0.02)
                assert not advanced
            else:
                assert advanced


@pytest.mark.asyncio
async def test_consumer_error_keeps_precedence_and_does_not_advance_source():
    advanced = False

    async def source():
        nonlocal advanced
        yield AgentMessage(type="assistant", content="partial")
        advanced = True
        raise ValueError("provider failed")

    with pytest.raises(RuntimeError, match="consumer failed"):
        async with isolated_runtime_stream(source()) as messages:
            async for _ in messages:
                raise RuntimeError("consumer failed")
    assert not advanced
