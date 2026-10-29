"""Opt-in structured batch route for the existing interview MCP tool.

Default interview behavior is unchanged. This route neither scores ambiguity nor
marks a session Seed-ready. Caller-owned dependencies are explicit input, not a
claim inferred from model output.
"""

import asyncio
from dataclasses import asdict
import json
import re
from typing import Any
import uuid

from ouroboros.bigbang.interview import InterviewState
from ouroboros.bigbang.question_batch import (
    QuestionBatch,
    generate_batch,
    native_payload,
    parse_text,
    render_text,
)
from ouroboros.core.file_lock import file_lock
from ouroboros.core.owner_only import write_owner_only
from ouroboros.core.security import InputValidator
from ouroboros.core.types import Result
from ouroboros.mcp.errors import MCPToolError
from ouroboros.mcp.types import MCPContentItem, MCPToolResult
from ouroboros.providers.base import CompletionConfig, Message, MessageRole


def _restore(raw: dict[str, Any]) -> QuestionBatch:
    from ouroboros.bigbang.question_batch import Choice, Question

    return QuestionBatch(
        tuple(
            Question(
                **{
                    key: value
                    for key, value in item.items()
                    if key not in ("choices", "recommended")
                },
                choices=tuple(Choice(**choice) for choice in item["choices"]),
                recommended=tuple(item["recommended"]),
            )
            for item in raw["questions"]
        )
    )


async def _save_if_current(engine: Any, state: InterviewState, expected: dict[str, Any]) -> Result:
    """Compare-and-save against the same lock used by ordinary state writers."""

    def write() -> bool:
        path = engine._state_file_path(state.interview_id)
        with file_lock(path, exclusive=True):
            current = InterviewState.model_validate_json(path.read_text(encoding="utf-8"))
            if current.model_dump(mode="json") != expected:
                raise ValueError("Interview changed during batch turn; resume before retrying")
            state.mark_updated()
            return write_owner_only(path, state.model_dump_json(indent=2))

    try:
        if not await asyncio.to_thread(write):
            raise ValueError("Batch persistence durability unconfirmed; resume to inspect state")
    except (OSError, ValueError) as exc:
        return Result.err(str(exc))
    return Result.ok(state)


async def handle_batch(handler: Any, arguments: dict[str, Any]) -> Result:
    """Run through production engine persistence and LLM adapter boundaries."""

    def error(message: str) -> Result:
        return Result.err(MCPToolError(message, tool_name="ouroboros_interview"))

    from ouroboros.mcp.tools.subagent import should_dispatch_via_plugin

    if should_dispatch_via_plugin(handler.agent_runtime_backend, handler.opencode_mode):
        return error("Structured batches currently require the in-process interview path")
    engine, adapter = handler._create_interview_engine()
    session_id = arguments.get("session_id")
    initial = arguments.get("initial_context")
    if initial and session_id:
        return error("A batch cannot start and resume in the same request")
    supplied_id = arguments.get("interview_id")
    if supplied_id is not None:
        if (
            not initial
            or not isinstance(supplied_id, str)
            or not re.fullmatch(r"interview_[0-9a-f]{16}", supplied_id)
        ):
            return error("interview_id must be a new server-format identifier")
        if (engine.state_dir / f"interview_{supplied_id}.json").exists():
            return error("interview_id already exists")
    capacity = arguments.get("batch_capacity", 4)
    if type(capacity) is not int or not 1 <= capacity <= 5:
        return error("batch_capacity must be an integer between one and five")
    if initial:
        result = await engine.start_interview(
            initial,
            interview_id=supplied_id or f"interview_{uuid.uuid4().hex[:16]}",
            cwd=arguments.get("cwd"),
        )
    elif isinstance(session_id, str) and session_id:
        result = await engine.load_state(session_id)
    else:
        return error("Provide initial_context to start or session_id to resume a batch")
    if result.is_err:
        return error(str(result.error))
    state: InterviewState = result.value
    if arguments.get("confused_terms") or arguments.get("references") or arguments.get("calibrate"):
        return error(
            "Use the ordinary interview route for reference/calibration context before a batch"
        )
    expected = state.model_dump(mode="json")
    if state.is_complete:
        return error("Completed interviews cannot accept batch turns")
    if state.rounds and state.rounds[-1].user_response is None:
        return error("Answer the existing single question before requesting a batch")
    if state.needs_initial_context_summary:
        return error("Summarize the initial context before requesting a batch")
    if state.pending_confused_terms or any(
        resolution.status.value != "resolved" for resolution in state.reference_resolutions
    ):
        return error(
            "Resolve pending terminology and reference questions on the ordinary route first"
        )
    pending = state.pending_question_batch
    answer = arguments.get("answer")
    if answer is not None:
        if not pending:
            return error("No pending batch to answer")
        if arguments.get("batch_id") != pending.get("batch_id"):
            return error("batch_id must match the pending batch; resume before answering")
        attempts = pending.get("attempts", 0)
        if attempts >= 3:
            return error("Batch answer retry limit reached; pending batch retained")
        try:
            batch = _restore(pending)
            answers = parse_text(batch, answer)
        except (ValueError, TypeError, KeyError):
            state.pending_question_batch = {**pending, "attempts": attempts + 1}
            saved = await _save_if_current(engine, state, expected)
            return error(
                "Invalid batch answer; use numbered choices or other: text"
                if saved.is_ok
                else str(saved.error)
            )
        # Validate the whole turn before recording any answer. Work on a copy so
        # a failure cannot leave a partially mutated in-memory interview state.
        candidate = state.model_copy(deep=True)
        candidate.pending_question_batch = None
        for question, response in zip(batch.questions, answers, strict=True):
            if response.free_text is not None:
                text = response.free_text
            else:
                text = json.dumps(
                    {
                        "selected": [
                            {"label": choice.label, "text": choice.text}
                            for choice in question.choices
                            if choice.label in response.selected
                        ],
                        "source": "user",
                        "option_sources": {
                            choice.label: choice.source
                            for choice in question.choices
                            if choice.label in response.selected
                        },
                    },
                    ensure_ascii=False,
                )
            valid, reason = InputValidator.validate_user_response(text)
            if not valid:
                return error(reason)
            recorded = await engine.record_response(candidate, text, question.text)
            if recorded.is_err:
                return error(str(recorded.error))
        candidate.pending_question_batch = None
        candidate.clear_stored_ambiguity()
        candidate.completion_candidate_streak = 0
        saved = await _save_if_current(engine, candidate, expected)
        if saved.is_err:
            return error(str(saved.error))
        return Result.ok(
            MCPToolResult(
                content=(
                    MCPContentItem(
                        type="text",
                        text="Batch answers recorded. Resume the interview for ambiguity scoring and the next question.",
                    ),
                ),
                meta={
                    "session_id": candidate.interview_id,
                    "batch_recorded": True,
                    "seed_ready": False,
                },
            )
        )
    if pending:
        batch = _restore(pending)
    else:
        ids = arguments.get("batch_question_ids")
        dependencies = arguments.get("batch_dependencies")
        if not isinstance(ids, list) or not isinstance(dependencies, dict):
            return error("Batch ids and explicit dependency map are required")

        async def complete(prompt: str) -> str:
            result = await adapter.complete(
                [Message(role=MessageRole.USER, content=prompt)],
                CompletionConfig(
                    model=engine.model, temperature=engine.temperature, max_tokens=engine.max_tokens
                ),
            )
            if result.is_err:
                raise ValueError(str(result.error))
            return result.value.content

        try:
            batch = await generate_batch(
                complete, tuple(ids), dependencies, state.model_dump_json()
            )
        except (ValueError, TypeError, KeyError) as exc:
            return error(f"Batch generation failed: {type(exc).__name__}; state retained")
        state.pending_question_batch = {
            **asdict(batch),
            "attempts": 0,
            "batch_id": uuid.uuid4().hex,
        }
        saved = await _save_if_current(engine, state, expected)
        if saved.is_err:
            return error(str(saved.error))
    capacity = arguments.get("batch_capacity", 4)
    try:
        chunks = batch.chunks(capacity)
    except ValueError as exc:
        return error(str(exc))
    return Result.ok(
        MCPToolResult(
            content=(MCPContentItem(type="text", text=render_text(batch)),),
            meta={
                "session_id": state.interview_id,
                "question_batches": [native_payload(chunk) for chunk in chunks],
                "batch_id": state.pending_question_batch["batch_id"],
                "independence": "caller_asserted_not_verified",
                "answer_contract": "Submit all numbered answers together using this batch_id; chunks are presentation only",
                "seed_ready": False,
            },
        )
    )
