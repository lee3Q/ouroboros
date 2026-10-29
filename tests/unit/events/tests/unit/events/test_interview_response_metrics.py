"""Character-count evidence for #1657, not a complete effort metric."""

import pytest

from ouroboros.events.interview import interview_response_recorded


@pytest.mark.parametrize("answer", ["", "short", "x" * 200, "x" * 201, "한글🙂e\u0301", "a\n b\t"])
def test_response_count_uses_complete_submitted_text(answer: str) -> None:
    event = interview_response_recorded("interview-1", 2, "question", answer)

    assert event.data["response_chars"] == len(answer)
    assert event.data["response_preview"] == answer[:200]
    assert event.type == "interview.response.recorded"
    assert event.aggregate_id == "interview-1"
    assert event.data["round_number"] == 2


def test_count_does_not_persist_text_beyond_existing_preview() -> None:
    answer = "x" * 200 + "PRIVATE-TAIL-NOT-FOR-PREVIEW"
    event = interview_response_recorded("interview-1", 1, "q" * 250, answer)

    assert event.data == {
        "round_number": 1,
        "question_preview": "q" * 200,
        "response_preview": "x" * 200,
        "response_chars": len(answer),
    }
    assert "PRIVATE-TAIL" not in str(event.to_db_dict())


def test_long_answers_with_same_preview_retain_distinct_counts() -> None:
    short = interview_response_recorded("i", 1, "q", "x" * 200)
    long = interview_response_recorded("i", 1, "q", "x" * 900)

    assert short.data["response_preview"] == long.data["response_preview"]
    assert short.data["response_chars"] == 200
    assert long.data["response_chars"] == 900
