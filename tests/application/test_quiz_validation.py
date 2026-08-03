from dataclasses import replace

import pytest

from app.application.quiz_validation import (
    align_quiz_citation_evidence,
    normalize_quiz_prompt,
    validate_quiz_rules,
)
from app.domain.chunk import DocumentChunk
from app.domain.quiz import QuestionType, Quiz


def _quiz_payload(
    question_type: str = "SINGLE_CHOICE",
) -> dict[str, object]:
    if question_type == "TRUE_FALSE":
        options = [
            {"option_id": "O", "text": "O"},
            {"option_id": "X", "text": "X"},
        ]
        correct_answer = {"option_id": "O"}
    else:
        options = [
            {"option_id": "1", "text": "선택지 1"},
            {"option_id": "2", "text": "선택지 2"},
            {"option_id": "3", "text": "선택지 3"},
            {"option_id": "4", "text": "선택지 4"},
        ]
        correct_answer = {"option_id": "1"}

    scenario_json = None
    usage_type = "SUB_CHAPTER"

    if question_type == "SCENARIO":
        usage_type = "MAIN_CHAPTER"
        scenario_json = {
            "character": "안정적인 저축을 원하는 학생",
            "financial_context": "매달 용돈을 받고 있다.",
            "constraints": ["원금 손실을 피해야 한다."],
        }

    return {
        "usage_type": usage_type,
        "question_type": question_type,
        "prompt": "예금에 대한 설명으로 올바른 것은?",
        "scenario_json": scenario_json,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
        "difficulty": "EASY",
        "citations": [
            {
                "chunk_key": "47:37",
                "evidence_text": ("예금은 금융기관에 돈을 맡기는 금융상품이다."),
            }
        ],
    }


def _quiz(
    question_type: str = "SINGLE_CHOICE",
    **changes: object,
) -> Quiz:
    payload = _quiz_payload(question_type)
    payload.update(changes)
    return Quiz.model_validate(payload)


def _chunks(count: int = 5) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            document_id="47",
            chunk_key=f"47:{37 + index}",
            sequence=37 + index,
            content=(
                "예금은 금융기관에 돈을 맡기는 금융상품이다."
                if index == 0
                else f"금융 교육 청크 {index}"
            ),
            title="금융 교과서",
            source="financial_textbook.txt",
        )
        for index in range(count)
    ]


@pytest.mark.parametrize(
    "question_type",
    ["TRUE_FALSE", "SINGLE_CHOICE", "SCENARIO"],
)
def test_accept_valid_quiz_rules(
    question_type: str,
) -> None:
    result = validate_quiz_rules(
        quiz=_quiz(question_type),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is True
    assert result.citation_valid is True
    assert result.duplicate is False
    assert result.errors == ()


@pytest.mark.parametrize(
    ("question_type", "usage_type"),
    [
        ("TRUE_FALSE", "MAIN_CHAPTER"),
        ("SINGLE_CHOICE", "MAIN_CHAPTER"),
        ("SCENARIO", "SUB_CHAPTER"),
    ],
)
def test_reject_usage_type_mismatch(
    question_type: str,
    usage_type: str,
) -> None:
    result = validate_quiz_rules(
        quiz=_quiz(question_type, usage_type=usage_type),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is False
    assert "usage_type_mismatch" in result.errors


def test_reject_question_type_different_from_request() -> None:
    result = validate_quiz_rules(
        quiz=_quiz("SCENARIO"),
        retrieved_chunks=_chunks(),
        expected_question_type=QuestionType.SINGLE_CHOICE,
    )

    assert result.answer_valid is False
    assert "question_type_mismatch" in result.errors


def test_reject_invalid_option_count() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(
            options=[
                {"option_id": "1", "text": "선택지 1"},
                {"option_id": "2", "text": "선택지 2"},
            ]
        ),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is False
    assert "invalid_option_count" in result.errors


def test_reject_duplicate_option_id() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(
            options=[
                {"option_id": "1", "text": "선택지 1"},
                {"option_id": "1", "text": "선택지 2"},
                {"option_id": "3", "text": "선택지 3"},
                {"option_id": "4", "text": "선택지 4"},
            ]
        ),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is False
    assert "duplicate_option_id" in result.errors


def test_reject_invalid_option_ids() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(
            options=[
                {"option_id": "1", "text": "선택지 1"},
                {"option_id": "2", "text": "선택지 2"},
                {"option_id": "3", "text": "선택지 3"},
                {"option_id": "5", "text": "선택지 5"},
            ]
        ),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is False
    assert "invalid_option_ids" in result.errors


def test_reject_invalid_true_false_option_text() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(
            "TRUE_FALSE",
            options=[
                {"option_id": "O", "text": "맞다"},
                {"option_id": "X", "text": "틀리다"},
            ],
        ),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is False
    assert "invalid_true_false_option_text" in result.errors


def test_reject_answer_not_in_options() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(correct_answer={"option_id": "5"}),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is False
    assert "correct_answer_not_found" in result.errors


def test_reject_blank_explanation() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(explanation="   "),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is False
    assert "explanation_required" in result.errors


@pytest.mark.parametrize(
    ("question_type", "scenario_json", "error_code"),
    [
        ("SCENARIO", None, "scenario_required"),
        (
            "SINGLE_CHOICE",
            {
                "character": "학생",
                "financial_context": "용돈을 받고 있다.",
                "constraints": [],
            },
            "scenario_not_allowed",
        ),
    ],
)
def test_reject_invalid_scenario_rule(
    question_type: str,
    scenario_json: dict[str, object] | None,
    error_code: str,
) -> None:
    result = validate_quiz_rules(
        quiz=_quiz(question_type, scenario_json=scenario_json),
        retrieved_chunks=_chunks(),
    )

    assert result.answer_valid is False
    assert error_code in result.errors


def test_require_at_least_one_citation() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(citations=[]),
        retrieved_chunks=_chunks(),
    )

    assert result.citation_valid is False
    assert result.errors == ("citation_required",)


def test_reject_citation_outside_top_five() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(
            citations=[
                {
                    "chunk_key": "47:42",
                    "evidence_text": "금융 교육 청크 5",
                }
            ]
        ),
        retrieved_chunks=_chunks(count=6),
    )

    assert result.citation_valid is False
    assert result.errors == ("citation_chunk_not_found:47:42",)


def test_reject_evidence_not_in_chunk_content() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(
            citations=[
                {
                    "chunk_key": "47:37",
                    "evidence_text": "실제 청크에 없는 문장",
                }
            ]
        ),
        retrieved_chunks=_chunks(),
    )

    assert result.citation_valid is False
    assert result.errors == ("citation_evidence_not_found:47:37",)


def test_align_whitespace_only_citation_evidence_to_original_chunk() -> None:
    chunks = _chunks()
    chunks[0] = replace(
        chunks[0],
        content=("정기 예금은 약정 기간 동안 인출하지 않는 예 금이다."),
    )
    quiz = _quiz(
        citations=[
            {
                "chunk_key": "47:37",
                "evidence_text": ("정기 예금은 약정 기간 동안 인출하지 않는 예금이다."),
            }
        ]
    )

    aligned_quiz = align_quiz_citation_evidence(
        quiz=quiz,
        retrieved_chunks=chunks,
    )

    assert aligned_quiz.citations[0].evidence_text == (
        "정기 예금은 약정 기간 동안 인출하지 않는 예 금이다."
    )
    assert aligned_quiz.citations[0].evidence_text in chunks[0].content


def test_do_not_align_citation_when_non_whitespace_text_differs() -> None:
    chunks = _chunks()
    chunks[0] = replace(
        chunks[0],
        content="예금은 약정 기간 동안 인출하지 않는 예금이다.",
    )
    quiz = _quiz(
        citations=[
            {
                "chunk_key": "47:37",
                "evidence_text": "예금은 약정 기간 동안 출금하지 않는 예금이다.",
            }
        ]
    )

    aligned_quiz = align_quiz_citation_evidence(
        quiz=quiz,
        retrieved_chunks=chunks,
    )
    result = validate_quiz_rules(
        quiz=aligned_quiz,
        retrieved_chunks=chunks,
    )

    assert aligned_quiz == quiz
    assert result.errors == ("citation_evidence_not_found:47:37",)


def test_normalize_whitespace_and_punctuation() -> None:
    assert normalize_quiz_prompt("예금은...  무엇인가?") == "예금은 무엇인가"


def test_detect_duplicate_prompt_after_normalization() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(prompt="예금은...  무엇인가?"),
        retrieved_chunks=_chunks(),
        existing_prompts=["예금은 무엇인가!"],
    )

    assert result.duplicate is True
    assert result.errors == ("duplicate_prompt",)


def test_do_not_mark_different_prompt_as_duplicate() -> None:
    result = validate_quiz_rules(
        quiz=_quiz(),
        retrieved_chunks=_chunks(),
        existing_prompts=["채권에 대한 설명으로 올바른 것은?"],
    )

    assert result.duplicate is False
    assert "duplicate_prompt" not in result.errors
