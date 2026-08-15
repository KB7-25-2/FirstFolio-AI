import random
from dataclasses import replace

import pytest

from app.application.quiz_validation import (
    align_quiz_citation_evidence,
    find_unsupported_numeric_claims,
    normalize_quiz_prompt,
    shuffle_quiz_options,
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
            "title": "금융상품 선택",
            "narrative": "안정적인 저축을 원하는 학생이 매달 용돈을 받고 있다.",
            "persona": {"name": "민서", "age": "18세", "job": "고등학생"},
            "requirements": {
                "assets": "매달 받는 용돈",
                "risk": "원금 손실을 피하고 싶음",
                "goal": "안정적으로 저축하기",
            },
            "market": {
                "title": "시장 정보",
                "reference_at": "2026-08-10T00:00:00Z",
                "bullets": ["검증된 시장 정보"],
            },
            "constraints": ["원금 손실을 피해야 한다."],
            "paper_title": "선택 보고서",
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
                "title": "금융상품 선택",
                "narrative": "학생이 용돈을 받고 있다.",
                "persona": {"name": "민서", "age": "18세", "job": "고등학생"},
                "requirements": {
                    "assets": "매달 받는 용돈",
                    "risk": "원금 손실을 피하고 싶음",
                    "goal": "안정적으로 저축하기",
                },
                "market": {
                    "title": "시장 정보",
                    "reference_at": "2026-08-10T00:00:00Z",
                    "bullets": ["검증된 시장 정보"],
                },
                "constraints": [],
                "paper_title": "선택 보고서",
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


def test_scenario_skips_all_numeric_check() -> None:
    chunks = _chunks()
    chunks[0] = replace(
        chunks[0],
        content=(
            "정기 예금의 약정 기간은 1개월 이상 5년 이내이다. "
            "일반적으로 예치 기간이 길수록 금리가 높아진다."
        ),
    )
    narrative = (
        "고등학생이 대학 진학을 위해 100만 원을 저축하려고 하며 상품마다 만기가 다르다."
    )
    correct_answer = "5년 후 만기, 이자율 4.0%"
    explanation = "100만 원을 5년 동안 4.0% 금리로 맡기는 것이 가장 유리하다."
    quiz = _quiz(
        "SCENARIO",
        prompt="5년 안에 어떤 정기 예금 상품을 선택해야 할까요?",
        scenario_json={
            "title": "정기 예금 선택",
            "narrative": narrative,
            "persona": {"name": "민서", "age": "18세", "job": "고등학생"},
            "requirements": {
                "assets": "저축 자금 100만 원",
                "risk": "원금 손실을 피하고 싶음",
                "goal": "대학 진학 자금 마련",
            },
            "market": {
                "title": "시장 정보",
                "reference_at": "2026-08-10T00:00:00Z",
                "bullets": ["검증된 시장 정보"],
            },
            "constraints": [
                "예치 기간이 1개월 이상 5년 이내",
                "중도 해지할 경우 낮은 금리 적용",
            ],
            "paper_title": "선택 보고서",
        },
        options=[
            {"option_id": "1", "text": "1개월 후 만기, 이자율 1.5%"},
            {"option_id": "2", "text": "1년 후 만기, 이자율 2.0%"},
            {"option_id": "3", "text": "3년 후 만기, 이자율 3.5%"},
            {"option_id": "4", "text": correct_answer},
        ],
        correct_answer={"option_id": "4"},
        explanation=explanation,
    )

    unsupported_claims = find_unsupported_numeric_claims(quiz, chunks)

    # SCENARIO는 prompt·선택지·해설 수치를 모두 검사하지 않으므로 항상 빈 튜플
    assert unsupported_claims == ()


def test_accept_numeric_claims_present_in_evidence() -> None:
    chunks = _chunks()
    chunks[0] = replace(
        chunks[0],
        content="정기 예금의 약정 기간은 5년 이내이다.",
    )
    quiz = _quiz(
        prompt="다음 4개 선택지 중 정기 예금의 약정 기간은 5년 이내인가?",
        explanation="정기 예금의 약정 기간은 5년 이내이다.",
    )

    assert find_unsupported_numeric_claims(quiz, chunks) == ()


def test_shuffle_quiz_options_keeps_true_false_unchanged() -> None:
    quiz = _quiz("TRUE_FALSE")

    shuffled = shuffle_quiz_options(quiz, rng=random.Random(1))

    assert shuffled == quiz


def test_shuffle_quiz_options_reorders_and_tracks_correct_answer() -> None:
    quiz = _quiz(
        "SINGLE_CHOICE",
        options=[
            {"option_id": "1", "text": "정답 선택지"},
            {"option_id": "2", "text": "오답 선택지 2"},
            {"option_id": "3", "text": "오답 선택지 3"},
            {"option_id": "4", "text": "오답 선택지 4"},
        ],
        correct_answer={"option_id": "1"},
    )

    shuffled = shuffle_quiz_options(quiz, rng=random.Random(7))

    assert [option.option_id for option in shuffled.options] == ["1", "2", "3", "4"]
    assert {option.text for option in shuffled.options} == {
        option.text for option in quiz.options
    }
    correct_option = next(
        option
        for option in shuffled.options
        if option.option_id == shuffled.correct_answer.option_id
    )
    assert correct_option.text == "정답 선택지"
    assert [option.text for option in shuffled.options] != [
        option.text for option in quiz.options
    ]


def test_shuffle_quiz_options_preserves_other_fields() -> None:
    quiz = _quiz("SCENARIO")

    shuffled = shuffle_quiz_options(quiz, rng=random.Random(3))

    assert shuffled.model_dump(exclude={"options", "correct_answer"}) == (
        quiz.model_dump(exclude={"options", "correct_answer"})
    )
