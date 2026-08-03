from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.dev_quiz_generations import get_quiz_generation_service
from app.application.quiz_generation import (
    QuizGenerationService,
    QuizGenerationValidationError,
)
from app.domain.quiz import (
    GroundingValidation,
    QuestionType,
    QuizGenerationResult,
)
from app.main import app


def _quiz_generation_result(
    question_type: QuestionType,
) -> QuizGenerationResult:
    if question_type == QuestionType.TRUE_FALSE:
        usage_type = "SUB_CHAPTER"
        scenario_json = None
        options = [
            {"option_id": "O", "text": "O"},
            {"option_id": "X", "text": "X"},
        ]
        correct_answer = {"option_id": "O"}
    else:
        usage_type = (
            "MAIN_CHAPTER" if question_type == QuestionType.SCENARIO else "SUB_CHAPTER"
        )
        scenario_json = (
            {
                "character": "안정적인 저축을 원하는 학생",
                "financial_context": "매달 일정한 용돈을 받고 있다.",
                "constraints": ["원금 손실을 피해야 한다."],
            }
            if question_type == QuestionType.SCENARIO
            else None
        )
        options = [
            {"option_id": "1", "text": "선택지 1"},
            {"option_id": "2", "text": "선택지 2"},
            {"option_id": "3", "text": "선택지 3"},
            {"option_id": "4", "text": "선택지 4"},
        ]
        correct_answer = {"option_id": "1"}

    return QuizGenerationResult.model_validate(
        {
            "quiz": {
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
                        "evidence_text": (
                            "예금은 금융기관에 돈을 맡기는 금융상품이다."
                        ),
                    }
                ],
            },
            "sources": [
                {
                    "document_id": 47,
                    "chunk_key": "47:37",
                    "title": "금융 교과서",
                    "heading": "저축과 저축 상품",
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
                "model": "gpt-4o-mini",
                "input_tokens": 160,
                "output_tokens": 100,
                "elapsed_ms": 250,
            },
        }
    )


@pytest.fixture
def quiz_generation_service() -> Mock:
    return Mock(spec=QuizGenerationService)


@pytest.fixture
def client(
    quiz_generation_service: Mock,
) -> Iterator[TestClient]:
    app.dependency_overrides[get_quiz_generation_service] = lambda: (
        quiz_generation_service
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(
            get_quiz_generation_service,
            None,
        )


@pytest.mark.parametrize(
    "question_type",
    [
        QuestionType.TRUE_FALSE,
        QuestionType.SINGLE_CHOICE,
        QuestionType.SCENARIO,
    ],
)
def test_create_quiz_generation(
    question_type: QuestionType,
    client: TestClient,
    quiz_generation_service: Mock,
) -> None:
    expected_result = _quiz_generation_result(question_type)
    quiz_generation_service.generate.return_value = expected_result

    response = client.post(
        "/api/v1/dev/quiz-generations",
        json={
            "question_type": question_type.value,
            "topic": "  예금의 특징  ",
        },
    )

    assert response.status_code == 200
    assert response.json() == expected_result.model_dump(mode="json")
    quiz_generation_service.generate.assert_called_once_with(
        question_type=question_type,
        topic="예금의 특징",
    )


def test_reject_unsupported_question_type(
    client: TestClient,
    quiz_generation_service: Mock,
) -> None:
    response = client.post(
        "/api/v1/dev/quiz-generations",
        json={
            "question_type": "MULTIPLE_CHOICE",
            "topic": "예금의 특징",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == [
        "body",
        "question_type",
    ]
    quiz_generation_service.generate.assert_not_called()


@pytest.mark.parametrize("topic", ["", "   "])
def test_reject_blank_topic(
    topic: str,
    client: TestClient,
    quiz_generation_service: Mock,
) -> None:
    response = client.post(
        "/api/v1/dev/quiz-generations",
        json={
            "question_type": "TRUE_FALSE",
            "topic": topic,
        },
    )

    assert response.status_code == 422
    assert any(error["loc"] == ["body", "topic"] for error in response.json()["detail"])
    quiz_generation_service.generate.assert_not_called()


def test_reject_unknown_request_field(
    client: TestClient,
    quiz_generation_service: Mock,
) -> None:
    response = client.post(
        "/api/v1/dev/quiz-generations",
        json={
            "question_type": "TRUE_FALSE",
            "topic": "예금의 특징",
            "count": 3,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == [
        "body",
        "count",
    ]
    quiz_generation_service.generate.assert_not_called()


def test_return_not_found_without_search_result(
    client: TestClient,
    quiz_generation_service: Mock,
) -> None:
    quiz_generation_service.generate.side_effect = QuizGenerationValidationError(
        ["search_result_required"],
        stage="search",
    )

    response = client.post(
        "/api/v1/dev/quiz-generations",
        json={
            "question_type": "TRUE_FALSE",
            "topic": "검색되지 않는 주제",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "stage": "search",
        "errors": ["search_result_required"],
        "reason": None,
        "unsupported_claims": [],
    }
    assert "quiz" not in response.json()


@pytest.mark.parametrize(
    "errors",
    [
        ["usage_type_mismatch", "scenario_required"],
        ["invalid_option_count", "correct_answer_not_found"],
        ["citation_chunk_not_found:47:99"],
        ["citation_evidence_not_found:47:37"],
    ],
    ids=[
        "quiz-rule",
        "options-and-answer",
        "citation",
        "evidence-text",
    ],
)
def test_return_generation_validation_failure(
    errors: list[str],
    client: TestClient,
    quiz_generation_service: Mock,
) -> None:
    quiz_generation_service.generate.side_effect = QuizGenerationValidationError(
        errors,
        stage="generation_validation",
    )

    response = client.post(
        "/api/v1/dev/quiz-generations",
        json={
            "question_type": "SINGLE_CHOICE",
            "topic": "예금의 특징",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "stage": "generation_validation",
        "errors": errors,
        "reason": None,
        "unsupported_claims": [],
    }
    assert "quiz" not in response.json()


def test_return_grounding_validation_failure(
    client: TestClient,
    quiz_generation_service: Mock,
) -> None:
    grounding_validation = GroundingValidation(
        supported=False,
        reason="해설의 핵심 주장을 검색 근거에서 확인할 수 없습니다.",
        unsupported_claims=["검색 근거에 없는 주장"],
    )
    quiz_generation_service.generate.side_effect = QuizGenerationValidationError(
        ["grounding_not_supported"],
        stage="grounding_validation",
        grounding_validation=grounding_validation,
    )

    response = client.post(
        "/api/v1/dev/quiz-generations",
        json={
            "question_type": "SCENARIO",
            "topic": "정기 예금 선택 상황",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "stage": "grounding_validation",
        "errors": ["grounding_not_supported"],
        "reason": grounding_validation.reason,
        "unsupported_claims": ["검색 근거에 없는 주장"],
    }
    assert "quiz" not in response.json()
