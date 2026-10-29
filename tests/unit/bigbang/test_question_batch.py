"""Presentation and generation contracts, not live-host or Seed equivalence."""

import json

import pytest

from ouroboros.bigbang.question_batch import (
    Choice,
    Question,
    QuestionBatch,
    TextAnswerSession,
    generate_batch,
    native_payload,
    parse_text,
    render_text,
    validate_answer,
)


def question(id="scope", multi=False):
    return Question(
        id,
        "Which scope?",
        (
            Choice("a", "Web", "generated"),
            Choice("b", "CLI", "document"),
            Choice("c", "Mobile", "user"),
        ),
        ("a",),
        "Use your own words",
        multi,
    )


def payload(ids=("scope",)):
    return json.dumps(
        {
            "questions": [
                {
                    "id": id,
                    "text": "Choose scope",
                    "choices": [
                        {"label": "a", "text": "Web", "source": "generated"},
                        {"label": "b", "text": "CLI", "source": "generated"},
                    ],
                    "recommended": ["a"],
                    "free_text_hint": "Your words",
                    "multi_select": True,
                }
                for id in ids
            ]
        }
    )


@pytest.mark.parametrize("selection", [(), ("a",), ("a", "c")])
def test_multiselect_accepts_zero_one_many(selection):
    assert validate_answer(question(multi=True), selection, None).selected == selection


@pytest.mark.parametrize("selection", [(), ("a", "b"), ("a", "a"), ("d",)])
def test_single_select_rejects_invalid(selection):
    with pytest.raises(ValueError):
        validate_answer(question(), selection, None)


@pytest.mark.parametrize(
    "reply,expected", [("1: a,c", ("a", "c")), ("1: 3,1", ("a", "c")), ("1: none", ())]
)
def test_text_native_roundtrip(reply, expected):
    batch = QuestionBatch((question(multi=True),))
    native = native_payload(batch)
    assert native[0]["id"] == "scope"
    text_answer = parse_text(batch, reply)[0]
    native_answer = validate_answer(batch.questions[0], expected, None)
    assert text_answer == native_answer
    assert "Select all that apply" in render_text(batch)
    assert "[generated]" in render_text(batch)
    assert "Recommended: a" in render_text(batch)


def test_free_text_is_explicit_and_preserved():
    batch = QuestionBatch((question(),))
    assert (
        parse_text(batch, "1: other: I want Rust/C++: not web")[0].free_text
        == "I want Rust/C++: not web"
    )
    with pytest.raises(ValueError):
        parse_text(batch, "1: Rust")
    with pytest.raises(ValueError):
        parse_text(batch, "1: other: ")


def test_numbered_slash_response_and_order():
    batch = QuestionBatch((question(), question("platform", True)))
    assert tuple(a.selected for a in parse_text(batch, "2: a,c / 1: 2")) == (("b",), ("a", "c"))


@pytest.mark.parametrize(
    "reply", ["1: a\n1: b", "2: a", "1: ", "1: 0", "1: 5", "1: a,a", "1: none", "1: a / 2: b"]
)
def test_invalid_answers_fail_closed(reply):
    with pytest.raises(ValueError):
        parse_text(QuestionBatch((question(),)), reply)


@pytest.mark.parametrize("capacity", [1, 2, 4, 10])
def test_host_chunks_preserve_exact_questions(capacity):
    batch = QuestionBatch(tuple(question(str(i)) for i in range(5)))
    chunks = batch.chunks(capacity)
    assert all(len(chunk.questions) <= capacity for chunk in chunks)
    assert tuple(q for chunk in chunks for q in chunk.questions) == batch.questions
    assert all(q is batch.questions[int(q.id)] for chunk in chunks for q in chunk.questions)


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5])
def test_invalid_capacity(capacity):
    with pytest.raises(ValueError):
        QuestionBatch((question(),)).chunks(capacity)


@pytest.mark.asyncio
async def test_whole_batch_is_exactly_one_model_call():
    calls = []

    async def complete(prompt):
        calls.append(prompt)
        return payload(("scope", "platform", "budget"))

    batch = await generate_batch(
        complete,
        ("scope", "platform", "budget"),
        {"scope": (), "platform": (), "budget": ()},
        "I want a web app",
    )
    assert len(calls) == 1
    assert len(batch.questions) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("deps", [{}, {"scope": ("platform",)}, {"scope": (), "extra": ()}])
async def test_dependencies_rejected_before_model_call(deps):
    async def complete(prompt):
        raise AssertionError("model must not run")

    with pytest.raises(ValueError):
        await generate_batch(complete, ("scope",), deps, "context")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        "not JSON",
        "[]",
        '{"questions": []}',
        payload(("other",)),
        '{"questions": [], "extra": true}',
    ],
)
async def test_bad_generation_has_no_hidden_repair(response):
    calls = []

    async def complete(prompt):
        calls.append(prompt)
        return response

    with pytest.raises((ValueError, TypeError)):
        await generate_batch(complete, ("scope",), {"scope": ()}, "context")
    assert len(calls) == 1


def test_retry_bound_and_no_implicit_defaults():
    session = TextAnswerSession(QuestionBatch((question(),)), max_attempts=2)
    for _ in range(2):
        with pytest.raises(ValueError):
            session.submit("bad")
    with pytest.raises(ValueError, match="retry limit"):
        session.submit("1: a")


def test_unselected_generated_options_are_not_user_decisions():
    answer = validate_answer(question(multi=True), ("b",), None)
    assert answer.source == "user"
    assert answer.selected == ("b",)
    assert "a" not in answer.selected and answer.free_text is None


def test_cancelled_generation_propagates():
    import asyncio

    async def complete(prompt):
        raise asyncio.CancelledError

    async def run():
        with pytest.raises(asyncio.CancelledError):
            await generate_batch(complete, ("scope",), {"scope": ()}, "context")

    asyncio.run(run())


@pytest.mark.asyncio
async def test_generated_source_claim_requires_caller_evidence():
    raw = json.loads(payload())
    raw["questions"][0]["choices"][0]["source"] = "user"

    async def complete(prompt):
        return json.dumps(raw)

    with pytest.raises(ValueError, match="caller evidence"):
        await generate_batch(complete, ("scope",), {"scope": ()}, "context")
    batch = await generate_batch(
        complete,
        ("scope",),
        {"scope": ()},
        "context",
        grounded_choices=frozenset({("scope", "Web", "user")}),
    )
    assert batch.questions[0].choices[0].source == "user"
