"""Actual MCP handler -> InterviewEngine -> saved JSON batch round trips."""

import json
from unittest.mock import AsyncMock

import pytest

from ouroboros.bigbang.interview import InterviewEngine
from ouroboros.core.types import Result
from ouroboros.mcp.tools.authoring_handlers import InterviewHandler
from ouroboros.providers.base import CompletionResponse, UsageInfo


def response():
    return CompletionResponse(
        content=json.dumps(
            {
                "questions": [
                    {
                        "id": id,
                        "text": text,
                        "choices": [
                            {"label": "a", "text": "Web", "source": "generated"},
                            {"label": "b", "text": "CLI", "source": "generated"},
                        ],
                        "recommended": ["a"],
                        "multi_select": multi,
                        "free_text_hint": "Your words",
                    }
                    for id, text, multi in [
                        ("scope", "Which scope?", True),
                        ("platform", "Which platform?", False),
                    ]
                ]
            }
        ),
        model="test",
        usage=UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        finish_reason="stop",
    )


@pytest.fixture
def route(tmp_path):
    adapter = AsyncMock()
    adapter.complete.return_value = Result.ok(response())
    engine = InterviewEngine(llm_adapter=adapter, state_dir=tmp_path, model="test")
    handler = InterviewHandler(
        interview_engine=engine,
        llm_adapter=adapter,
        llm_backend="claude",
        agent_runtime_backend="claude",
    )
    return handler, engine, adapter


async def start(handler):
    return await handler.handle(
        {
            "question_batch": True,
            "initial_context": "Build an app",
            "batch_question_ids": ["scope", "platform"],
            "batch_dependencies": {"scope": [], "platform": []},
            "batch_capacity": 1,
        }
    )


@pytest.mark.asyncio
async def test_actual_route_single_generation_persistent_resume_and_answer(route):
    handler, engine, adapter = route
    result = await start(handler)
    assert result.is_ok, result
    meta = result.value.meta
    session = meta["session_id"]
    assert adapter.complete.await_count == 1
    assert len(meta["question_batches"]) == 2
    state = (await engine.load_state(session)).value
    assert state.pending_question_batch and not state.rounds
    # Resume returns the exact persisted batch without another generation.
    resumed = await handler.handle({"question_batch": True, "session_id": session})
    assert resumed.is_ok
    assert resumed.value.content[0].text == result.value.content[0].text
    assert adapter.complete.await_count == 1
    answered = await handler.handle(
        {
            "question_batch": True,
            "session_id": session,
            "batch_id": result.value.meta["batch_id"],
            "answer": "1: a,b / 2: other: Linux only",
        }
    )
    assert answered.is_ok
    saved = (await engine.load_state(session)).value
    assert saved.pending_question_batch is None
    assert len(saved.rounds) == 2
    assert saved.rounds[0].question == "Which scope?"
    assert '"source": "user"' in saved.rounds[0].user_response
    assert saved.rounds[1].user_response == "Linux only"
    assert saved.ambiguity_score is None
    assert answered.value.meta["seed_ready"] is False
    assert adapter.complete.await_count == 1


@pytest.mark.asyncio
async def test_invalid_partial_answer_is_atomic_and_retries_persist(route):
    handler, engine, adapter = route
    result = await start(handler)
    session = result.value.meta["session_id"]
    for count in range(1, 4):
        invalid = await handler.handle(
            {
                "question_batch": True,
                "session_id": session,
                "batch_id": result.value.meta["batch_id"],
                "answer": "1: a",
            }
        )
        assert invalid.is_err
        saved = (await engine.load_state(session)).value
        assert saved.rounds == []
        assert saved.pending_question_batch["attempts"] == count
    blocked = await handler.handle(
        {
            "question_batch": True,
            "session_id": session,
            "batch_id": result.value.meta["batch_id"],
            "answer": "1: a / 2: b",
        }
    )
    assert blocked.is_err
    assert "retry limit" in str(blocked.error)


@pytest.mark.asyncio
async def test_pending_batch_cannot_be_answered_as_single_question(route):
    handler, engine, adapter = route
    result = await start(handler)
    saved = (await engine.load_state(result.value.meta["session_id"])).value
    assert (await engine.record_response(saved, "yes", "fake")).is_err
    assert (await engine.ask_next_question(saved)).is_err
    assert saved.rounds == []


@pytest.mark.asyncio
async def test_dependent_decision_rejected_before_generation(route):
    handler, engine, adapter = route
    result = await handler.handle(
        {
            "question_batch": True,
            "initial_context": "Build an app",
            "batch_question_ids": ["scope"],
            "batch_dependencies": {"scope": ["platform"]},
        }
    )
    assert result.is_err
    adapter.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_schema_and_single_question_path_remain(route):
    handler, engine, adapter = route
    assert {p.name for p in handler.definition.parameters} >= {
        "question_batch",
        "batch_question_ids",
        "batch_dependencies",
        "answer",
    }
    created = await engine.start_interview("Build an app")
    recorded = await engine.record_response(created.value, "CLI", "Which scope?")
    assert recorded.is_ok
    assert recorded.value.rounds[0].user_response == "CLI"


@pytest.mark.asyncio
async def test_stale_id_cannot_record_answers(route):
    handler, engine, adapter = route
    result = await start(handler)
    session = result.value.meta["session_id"]
    invalid = await handler.handle(
        {"question_batch": True, "session_id": session, "batch_id": "old", "answer": "1: a / 2: b"}
    )
    assert invalid.is_err
    assert (await engine.load_state(session)).value.rounds == []


@pytest.mark.asyncio
async def test_compare_save_rejects_stale_generation(route):
    from ouroboros.mcp.tools.interview_batch import _save_if_current

    handler, engine, adapter = route
    result = await start(handler)
    session = result.value.meta["session_id"]
    old = (await engine.load_state(session)).value
    expected = old.model_dump(mode="json")
    current = old.model_copy(deep=True)
    current.initial_context = "A newer actual user context"
    await engine.save_state(current)
    old.pending_question_batch = None
    saved = await _save_if_current(engine, old, expected)
    assert saved.is_err
    reread = (await engine.load_state(session)).value
    assert reread.initial_context == "A newer actual user context"
    assert reread.pending_question_batch is not None


@pytest.mark.asyncio
async def test_duplicate_concurrent_answers_commit_once(route):
    import asyncio

    handler, engine, adapter = route
    result = await start(handler)
    arguments = {
        "question_batch": True,
        "session_id": result.value.meta["session_id"],
        "batch_id": result.value.meta["batch_id"],
        "answer": "1: none / 2: a",
    }
    results = await asyncio.gather(handler.handle(arguments), handler.handle(arguments))
    assert sum(result.is_ok for result in results) == 1
    saved = (await engine.load_state(arguments["session_id"])).value
    assert len(saved.rounds) == 2
    assert '"selected": []' in saved.rounds[0].user_response
