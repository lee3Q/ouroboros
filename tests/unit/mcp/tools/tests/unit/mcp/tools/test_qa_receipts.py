"""Completed QA evaluations have a distinct, durable query receipt."""

from unittest.mock import AsyncMock

import pytest

from ouroboros.core.types import Result
from ouroboros.mcp.tools.qa import QAHandler
from ouroboros.mcp.tools.query_handlers import SessionStatusHandler
from ouroboros.persistence.event_store import EventStore
from ouroboros.providers.base import CompletionResponse, UsageInfo


@pytest.mark.asyncio
async def test_completed_qa_is_queryable_after_reopening_store(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'qa.db'}"
    store = EventStore(url)
    await store.initialize()
    adapter = AsyncMock()
    adapter.complete.return_value = Result.ok(
        CompletionResponse(content='{"score": 0.42}', model="fake", usage=UsageInfo(0, 0, 0))
    )
    try:
        result = await QAHandler(
            event_store=store, llm_adapter=adapter, llm_backend="claude_code"
        ).handle({"artifact": "PRIVATE ARTIFACT", "quality_bar": "PRIVATE BAR"})
        assert result.is_ok
        session_id = result.value.meta["qa_session_id"]
    finally:
        await store.close()
    reopened = EventStore(url)
    await reopened.initialize()
    try:
        status = await SessionStatusHandler(event_store=reopened).handle({"session_id": session_id})
        assert status.is_ok, status.error
        assert status.value.meta["session_kind"] == "qa"
        assert status.value.meta["status"] == "evaluated"
        assert status.value.meta["passed"] is False
        assert status.value.meta["score"] == 0.42
        assert status.value.meta["is_active"] is False
        assert "Execution ID:" not in status.value.content[0].text
        events = await reopened.replay("qa", session_id)
        assert len(events) == 1
        assert "PRIVATE" not in str(events[0].data)
        assert await reopened.replay("session", session_id) == []
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_failed_receipt_write_does_not_claim_durable_success():
    store = AsyncMock()
    store.append.side_effect = RuntimeError("database unavailable")
    adapter = AsyncMock()
    adapter.complete.return_value = Result.ok(
        CompletionResponse(content='{"score": 0.9}', model="fake", usage=UsageInfo(0, 0, 0))
    )
    result = await QAHandler(
        event_store=store, llm_adapter=adapter, llm_backend="claude_code"
    ).handle({"artifact": "example", "quality_bar": "works"})
    assert result.is_err
    assert "database unavailable" in str(result.error)


@pytest.mark.asyncio
async def test_no_store_explicitly_marks_receipt_unpersisted():
    adapter = AsyncMock()
    adapter.complete.return_value = Result.ok(
        CompletionResponse(content='{"score": 0.9}', model="fake", usage=UsageInfo(0, 0, 0))
    )
    result = await QAHandler(llm_adapter=adapter, llm_backend="claude_code").handle(
        {"artifact": "example", "quality_bar": "works"}
    )
    assert result.is_ok
    assert result.value.meta["receipt_persisted"] is False


@pytest.mark.asyncio
async def test_repeated_qa_queries_latest_durable_verdict():
    store = EventStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    try:
        adapter = AsyncMock()
        handler = QAHandler(event_store=store, llm_adapter=adapter, llm_backend="claude_code")
        for score in (0.1, 0.9):
            adapter.complete.return_value = Result.ok(
                CompletionResponse(
                    content=f'{{"score": {score}}}', model="fake", usage=UsageInfo(0, 0, 0)
                )
            )
            result = await handler.handle(
                {"artifact": "example", "quality_bar": "works", "qa_session_id": "qa-loop"}
            )
            assert result.is_ok
        result = await SessionStatusHandler(event_store=store).handle({"session_id": "qa-loop"})
        assert result.is_ok
        assert result.value.meta["score"] == 0.9
        assert result.value.meta["passed"] is True
        assert len(await store.replay("qa", "qa-loop")) == 2
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_missing_qa_still_returns_not_found():
    store = EventStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    try:
        result = await SessionStatusHandler(event_store=store).handle({"session_id": "qa-missing"})
        assert result.is_err
        assert "Session not found" in str(result.error)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_plugin_handoff_does_not_persist_completed_qa_receipt():
    store = EventStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    try:
        result = await QAHandler(
            event_store=store, agent_runtime_backend="opencode", opencode_mode="plugin"
        ).handle({"artifact": "example", "quality_bar": "works", "qa_session_id": "qa-plugin"})
        assert result.is_ok
        assert await store.replay("qa", "qa-plugin") == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_llm_failure_does_not_persist_completed_qa_receipt():
    store = EventStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    adapter = AsyncMock()
    adapter.complete.return_value = Result.err("provider unavailable")
    try:
        result = await QAHandler(
            event_store=store, llm_adapter=adapter, llm_backend="claude_code"
        ).handle({"artifact": "example", "quality_bar": "works", "qa_session_id": "qa-failed"})
        assert result.is_err
        assert await store.replay("qa", "qa-failed") == []
    finally:
        await store.close()
