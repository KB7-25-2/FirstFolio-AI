import pytest
from pydantic import ValidationError

from app.domain.quiz import (
    GroundingValidation,
    Quiz,
    QuizBatchError,
    QuizBatchInput,
    QuizBatchItemInput,
    QuizBatchRecord,
    QuizBatchStatus,
    QuizGenerationResult,
)


def _valid_payload(
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
            "narrative": "안정적인 저축을 원하는 고등학생이 매달 일정한 용돈을 받고 있다.",
            "persona": {"name": "민서", "age": "18세", "job": "고등학생"},
            "requirements": {
                "assets": "매달 받는 용돈",
                "risk": "원금 손실을 피하고 싶음",
                "goal": "안정적으로 저축하기",
            },
            "market": {
                "title": "시장 정보",
                "bullets": ["검증된 시장 정보"],
            },
            "constraints": [
                "원금 손실을 피해야 한다.",
            ],
            "paper_title": "선택 보고서",
        }

    return {
        "usage_type": usage_type,
        "question_type": question_type,
        "prompt": "예금에 대한 설명으로 옳은 것은?",
        "scenario_json": scenario_json,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
        "difficulty": "EASY",
        "citations": [
            {
                "chunk_key": "47:37",
                "evidence_text": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
            }
        ],
    }


@pytest.mark.parametrize(
    "question_type",
    [
        "TRUE_FALSE",
        "SINGLE_CHOICE",
        "SCENARIO",
    ],
)
def test_accept_supported_question_type(
    question_type: str,
) -> None:
    quiz = Quiz.model_validate(_valid_payload(question_type))

    assert quiz.question_type.value == question_type


def test_dump_quiz_with_expected_field_names() -> None:
    quiz = Quiz.model_validate(_valid_payload())

    result = quiz.model_dump(mode="json")

    assert set(result) == {
        "usage_type",
        "question_type",
        "prompt",
        "scenario_json",
        "options",
        "correct_answer",
        "explanation",
        "difficulty",
        "citations",
    }
    assert result["question_type"] == "SINGLE_CHOICE"
    assert result["correct_answer"] == {"option_id": "1"}


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("usage_type", "NEWS"),
        ("question_type", "MULTIPLE_CHOICE"),
        ("difficulty", "VERY_HARD"),
    ],
)
def test_reject_unsupported_enum_value(
    field_name: str,
    invalid_value: str,
) -> None:
    payload = _valid_payload()
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        Quiz.model_validate(payload)


def test_reject_missing_required_field() -> None:
    payload = _valid_payload()
    payload.pop("explanation")

    with pytest.raises(ValidationError):
        Quiz.model_validate(payload)


def test_reject_unknown_quiz_field() -> None:
    payload = _valid_payload()
    payload["choices"] = []

    with pytest.raises(ValidationError):
        Quiz.model_validate(payload)


def test_reject_unknown_nested_field() -> None:
    payload = _valid_payload()
    options = payload["options"]

    assert isinstance(options, list)
    options[0]["unexpected"] = True

    with pytest.raises(ValidationError):
        Quiz.model_validate(payload)


def test_reject_wrong_options_type() -> None:
    payload = _valid_payload()
    payload["options"] = "A, B, C, D"

    with pytest.raises(ValidationError):
        Quiz.model_validate(payload)


def _valid_result_payload() -> dict[str, object]:
    return {
        "quiz": _valid_payload(),
        "sources": [
            {
                "document_id": 47,
                "chunk_key": "47:37",
                "title": "금융 교과서",
                "heading": None,
                "source_url": None,
                "published_at": None,
                "evidence_text": ("예금은 금융기관에 돈을 맡기는 금융상품이다."),
            }
        ],
        "validation": {
            "schema_valid": True,
            "answer_valid": True,
            "citation_valid": True,
            "grounded": True,
            "duplicate": False,
            "errors": [],
        },
        "execution": {
            "model": "test-generation-model",
            "input_tokens": 100,
            "output_tokens": 50,
            "elapsed_ms": 1200,
        },
    }


def test_accept_quiz_generation_result() -> None:
    result = QuizGenerationResult.model_validate(_valid_result_payload())

    dumped = result.model_dump(mode="json")

    assert set(dumped) == {
        "quiz",
        "sources",
        "validation",
        "execution",
    }
    assert dumped["sources"][0]["document_id"] == 47
    assert dumped["execution"]["model"] == "test-generation-model"


def test_accept_nullable_source_metadata() -> None:
    result = QuizGenerationResult.model_validate(_valid_result_payload())
    source = result.sources[0]

    assert source.heading is None
    assert source.source_url is None
    assert source.published_at is None


@pytest.mark.parametrize(
    "field_name",
    [
        "input_tokens",
        "output_tokens",
        "elapsed_ms",
    ],
)
def test_reject_negative_execution_value(
    field_name: str,
) -> None:
    payload = _valid_result_payload()
    execution = payload["execution"]

    assert isinstance(execution, dict)
    execution[field_name] = -1

    with pytest.raises(ValidationError):
        QuizGenerationResult.model_validate(payload)


def test_reject_unknown_result_field() -> None:
    payload = _valid_result_payload()
    payload["request_id"] = "request-001"

    with pytest.raises(ValidationError):
        QuizGenerationResult.model_validate(payload)


def test_accept_grounding_validation_result() -> None:
    result = GroundingValidation.model_validate(
        {
            "supported": False,
            "reason": "검색 근거로 해설을 뒷받침할 수 없다.",
            "unsupported_claims": [
                "예금은 항상 물가상승률보다 높은 수익률을 제공한다.",
            ],
        }
    )

    assert result.supported is False
    assert len(result.unsupported_claims) == 1


def test_reject_unknown_grounding_validation_field() -> None:
    with pytest.raises(ValidationError):
        GroundingValidation.model_validate(
            {
                "supported": True,
                "reason": "검색 근거로 뒷발됨",
                "unsupported_claims": [],
                "confidence": 0.99,
            }
        )


def test_accept_batch_input_with_default_count() -> None:
    batch_input = QuizBatchInput.model_validate(
        {
            "items": [
                {
                    "question_type": "TRUE_FALSE",
                    "topic": "예금",
                }
            ]
        }
    )

    assert batch_input.items[0].count == 1


def test_reject_batch_record_with_status_payload_mismatch() -> None:
    with pytest.raises(ValidationError, match="상태와 결과 필드 조합"):
        QuizBatchRecord(
            batch_id="00000000-0000-0000-0000-000000000001",
            item_id="00000000-0000-0000-0000-000000000002",
            status=QuizBatchStatus.FAILED,
            input=QuizBatchItemInput(
                question_type="TRUE_FALSE",
                topic="예금",
            ),
            result=None,
            error=QuizBatchError(
                stage="search",
                errors=["search_result_required"],
                reason="검색 결과가 없습니다.",
                unsupported_claims=[],
            ),
            duplicate={
                "original_item_id": "00000000-0000-0000-0000-000000000003",
                "prompt": "중복 질문",
            },
        )
