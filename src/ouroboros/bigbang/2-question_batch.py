"""Host-neutral interview question batches (#1651, #1652, #1653).

This is a presentation boundary, not a planner or a Seed mutation API. A caller
must establish independence before generation. Unknown dependency declarations
fail closed; the model cannot certify its own question independence.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import json
import re
from typing import Literal


@dataclass(frozen=True, slots=True)
class Choice:
    label: str
    text: str
    source: Literal["user", "document", "generated"]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-d]", self.label):
            raise ValueError("choice label must be a, b, c, or d")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("choice text must be nonblank")
        if self.source not in ("user", "document", "generated"):
            raise ValueError("choice source must be explicit")


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    text: str
    choices: tuple[Choice, ...]
    recommended: tuple[str, ...]
    free_text_hint: str
    multi_select: bool = False
    multi_select_hint: str = "Select all that apply; use none for zero selections."

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", self.id):
            raise ValueError("question id must be a stable identifier")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("question text must be nonblank")
        if not isinstance(self.choices, tuple) or not 2 <= len(self.choices) <= 4:
            raise ValueError("question needs two to four immutable choices")
        if not all(isinstance(choice, Choice) for choice in self.choices):
            raise ValueError("invalid choice")
        labels = tuple(choice.label for choice in self.choices)
        if labels != tuple("abcd"[: len(labels)]):
            raise ValueError("choice labels must be sequential and unique")
        if type(self.multi_select) is not bool:
            raise ValueError("multi_select must be boolean")
        if not isinstance(self.recommended, tuple) or not self.recommended:
            raise ValueError("recommendation must name at least one choice")
        if len(set(self.recommended)) != len(self.recommended):
            raise ValueError("duplicate recommendation")
        if any(label not in labels for label in self.recommended):
            raise ValueError("recommendation must name an existing choice")
        if not self.multi_select and len(self.recommended) != 1:
            raise ValueError("single-select recommendation must name one choice")
        for hint in (self.free_text_hint, self.multi_select_hint):
            if not isinstance(hint, str) or not hint.strip():
                raise ValueError("answer hints must be nonblank")


@dataclass(frozen=True, slots=True)
class QuestionBatch:
    questions: tuple[Question, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.questions, tuple) or not 1 <= len(self.questions) <= 5:
            raise ValueError("batch must contain one to five immutable questions")
        if not all(isinstance(question, Question) for question in self.questions):
            raise ValueError("invalid question")
        if len({question.id for question in self.questions}) != len(self.questions):
            raise ValueError("duplicate question id")

    def chunks(self, capacity: int) -> tuple[QuestionBatch, ...]:
        if type(capacity) is not int or capacity < 1:
            raise ValueError("host capacity must be a positive integer")
        return tuple(
            QuestionBatch(self.questions[index : index + capacity])
            for index in range(0, len(self.questions), capacity)
        )


@dataclass(frozen=True, slots=True)
class Answer:
    question_id: str
    selected: tuple[str, ...] = ()
    free_text: str | None = None
    # Selected options are user decisions; unselected generated choices are NOT
    # negative user decisions. No implicit default or recommendation acceptance.
    source: Literal["user"] = "user"


def validate_answer(question: Question, selected: tuple[str, ...], text: str | None) -> Answer:
    if not isinstance(selected, tuple) or any(not isinstance(x, str) for x in selected):
        raise ValueError("selection must be an immutable tuple of labels")
    if text is not None:
        if not isinstance(text, str) or not text.strip() or selected:
            raise ValueError("free text must be nonblank and exclusive of selection")
        return Answer(question.id, free_text=text.strip())
    labels = {choice.label for choice in question.choices}
    if len(set(selected)) != len(selected) or any(label not in labels for label in selected):
        raise ValueError("unknown or duplicate selection")
    if not question.multi_select and len(selected) != 1:
        raise ValueError("single-select requires exactly one choice")
    # Canonical order does not depend on the renderer's selection ordering.
    return Answer(
        question.id, tuple(choice.label for choice in question.choices if choice.label in selected)
    )


def render_text(batch: QuestionBatch) -> str:
    lines: list[str] = []
    for index, question in enumerate(batch.questions, 1):
        lines.append(f"{index}: {question.text}")
        if question.multi_select:
            lines.append(question.multi_select_hint)
        for choice in question.choices:
            lines.append(f"  {choice.label}. {choice.text} [{choice.source}]")
        lines.append(f"  Recommended: {','.join(question.recommended)}")
        lines.append(f"  other: {question.free_text_hint}")
    lines.append("Reply with numbered answers, one per line: 1: a / 2: a,c / 3: other: your words")
    return "\n".join(lines)


def native_payload(batch: QuestionBatch) -> tuple[dict[str, object], ...]:
    """Return runtime-neutral presentation data; an actual host adapter owns UI."""
    return tuple(
        {
            "id": question.id,
            "question": question.text,
            "choices": tuple(
                {"label": choice.label, "text": choice.text, "source": choice.source}
                for choice in question.choices
            ),
            "recommended": question.recommended,
            "multi_select": question.multi_select,
            "free_text_hint": question.free_text_hint,
            "multi_select_hint": question.multi_select_hint if question.multi_select else None,
        }
        for question in batch.questions
    )


def parse_text(batch: QuestionBatch, response: str) -> tuple[Answer, ...]:
    if not isinstance(response, str):
        raise ValueError("response must be text")
    parts = re.split(r"(?:\n| / )(?=\d+:)", response.strip())
    by_number: dict[int, Answer] = {}
    for part in parts:
        match = re.fullmatch(r"(\d+):\s*(.*)", part, re.DOTALL)
        if not match:
            raise ValueError("use numbered answers")
        index = int(match[1])
        if not 1 <= index <= len(batch.questions) or index in by_number:
            raise ValueError("unknown or duplicate question number")
        question = batch.questions[index - 1]
        value = match[2].strip()
        if value.startswith("other:"):
            answer = validate_answer(question, (), value[6:])
        elif value.lower() == "none":
            answer = validate_answer(question, (), None)
        else:
            selected: list[str] = []
            for token in value.split(","):
                token = token.strip().lower()
                if re.fullmatch(r"[1-4]", token):
                    token = "abcd"[int(token) - 1]
                selected.append(token)
            answer = validate_answer(question, tuple(selected), None)
        by_number[index] = answer
    if len(by_number) != len(batch.questions):
        raise ValueError("every question requires an explicit answer")
    return tuple(by_number[index] for index in range(1, len(batch.questions) + 1))


async def generate_batch(
    complete: Callable[[str], Awaitable[str]],
    independent_ids: tuple[str, ...],
    dependencies: dict[str, tuple[str, ...]],
    context: str,
    *,
    grounded_choices: frozenset[tuple[str, str, str]] = frozenset(),
) -> QuestionBatch:
    """Generate exactly one batch in one call, using caller-owned dependencies.

    This boundary rejects any dependent question. A caller must schedule those
    after their prerequisites, not ask the model to ignore the dependency.
    Invalid generation raises without a hidden repair call or partial batch.
    """
    if not isinstance(independent_ids, tuple) or not 1 <= len(independent_ids) <= 5:
        raise ValueError("one to five independent question ids are required")
    if any(
        not isinstance(id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", id) for id in independent_ids
    ):
        raise ValueError("invalid independent question id")
    if len(set(independent_ids)) != len(independent_ids):
        raise ValueError("duplicate independent id")
    if set(dependencies) != set(independent_ids) or any(
        not isinstance(value, (tuple, list)) or value for value in dependencies.values()
    ):
        raise ValueError("independence must be explicitly established by the caller")
    prompt = (
        "Return only a JSON object with questions, in the supplied id order. "
        "Each question needs id, text, choices (2-4 objects with label a-d, text, "
        "source=user|document|generated), recommended (label array), free_text_hint, "
        "multi_select (boolean), multi_select_hint. Use the conversation language "
        "for text and hints. Generated options are hypotheses, not user facts. "
        "Only generate these independent decisions: "
        + json.dumps(independent_ids)
        + "\nContext:\n"
        + context
    )
    response = await complete(prompt)
    if not isinstance(response, str) or len(response) > 32000:
        raise ValueError("generated batch exceeds the bounded presentation size")
    payload = json.loads(response)
    if not isinstance(payload, dict) or set(payload) != {"questions"}:
        raise ValueError("expected a question batch object")
    raw = payload["questions"]
    if not isinstance(raw, list):
        raise ValueError("questions must be an array")
    questions = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("question must be an object")
        data = dict(item)
        choices = data.pop("choices", None)
        recommendation = data.pop("recommended", None)
        if not isinstance(choices, list) or not isinstance(recommendation, list):
            raise ValueError("choices and recommendation must be arrays")
        questions.append(
            Question(
                **data,
                choices=tuple(Choice(**choice) for choice in choices),
                recommended=tuple(recommendation),
            )
        )
    batch = QuestionBatch(tuple(questions))
    for question in batch.questions:
        for choice in question.choices:
            if (
                choice.source != "generated"
                and (question.id, choice.text, choice.source) not in grounded_choices
            ):
                raise ValueError("model claimed a source absent from caller evidence")
    if tuple(question.id for question in batch.questions) != independent_ids:
        raise ValueError("generated batch changed the requested decisions")
    return batch


@dataclass(slots=True)
class TextAnswerSession:
    """Bounded re-prompt state; invalid responses never advance the interview."""

    batch: QuestionBatch
    max_attempts: int = 3
    attempts: int = 0

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 5:
            raise ValueError("answer attempts must be between one and five")

    def submit(self, response: str) -> tuple[Answer, ...]:
        if self.attempts >= self.max_attempts:
            raise ValueError("answer retry limit reached")
        self.attempts += 1
        return parse_text(self.batch, response)
