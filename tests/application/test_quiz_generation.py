from unittest.mock import Mock

import pytest

from app.application.ports.quiz_model import (
    GroundingModelResult,
    QuizModelClient,
    QuizModelResult,
)
from app.application.quiz_generation import (
    QuizGenerationService,
    QuizGenerationValidationError,
)
from app.application.search.hybrid import HybridSearch
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.quiz import GroundingValidation, QuestionType, Quiz
from app.domain.search import SearchResult
from app.infrastructure.repositories.in_memory_chunk import InMemoryChunkRepository


def _chunks(count: int = 6) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            document_id="47",
            chunk_key=f"47:{index}",
            sequence=index,
            content=(
                "예금은 금융기관에 돈을 맡기는 금융상품이다."
                if index == 0
                else f"금융 교육 근거 {index}"
            ),
            title="금융 교과서",
            source="financial_textbook.txt",
            heading="저축과 저축 상품",
        )
        for index in range(count)
    ]


def _quiz(
    question_type: QuestionType = QuestionType.SINGLE_CHOICE,
    **changes: object,
) -> Quiz:
    if question_type == QuestionType.TRUE_FALSE:
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

    if question_type == QuestionType.SCENARIO:
        usage_type = "MAIN_CHAPTER"
        scenario_json = {
            "character": "안정적인 저축을 원하는 학생",
            "financial_context": "매달 용돈을 받고 있다.",
            "constraints": ["원금 손실을 피해야 한다."],
        }

    payload: dict[str, object] = {
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
                "chunk_key": "47:0",
                "evidence_text": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
            }
        ],
    }
    payload.update(changes)
    return Quiz.model_validate(payload)


def _service(
    *,
    quiz: Quiz | None = None,
    search_results: list[SearchResult] | None = None,
    supported: bool = True,
) -> tuple[
    QuizGenerationService,
    Mock,
    InMemoryChunkRepository,
]:
    chunks = _chunks()
    repository = InMemoryChunkRepository()
    repository.save_all(chunks)
    hybrid_search = Mock(spec=HybridSearch)
    hybrid_search.search.return_value = (
        search_results
        if search_results is not None
        else [SearchResult(chunk=chunk, score=1.0) for chunk in chunks]
    )
    model_client = Mock(spec=QuizModelClient)
    model_client.generate_quiz.return_value = QuizModelResult(
        quiz=quiz or _quiz(),
        input_tokens=120,
        output_tokens=80,
    )
    model_client.validate_grounding.return_value = GroundingModelResult(
        validation=GroundingValidation(
            supported=supported,
            reason=(
                "검색 근거로 뒷받침됩니다." if supported else "검색 근거가 부족합니다."
            ),
            unsupported_claims=[] if supported else ["근거 없는 주장"],
        ),
        input_tokens=40,
        output_tokens=20,
    )
    service = QuizGenerationService(
        settings=Settings(
            generation_model="gpt-4o-mini",
            _env_file=None,
        ),
        hybrid_search=hybrid_search,
        chunk_repository=repository,
        model_client=model_client,
    )
    return service, model_client, repository


@pytest.mark.parametrize(
    "question_type",
    [
        QuestionType.TRUE_FALSE,
        QuestionType.SINGLE_CHOICE,
        QuestionType.SCENARIO,
    ],
)
def test_generate_valid_quiz_result(
    question_type: QuestionType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, model_client, _ = _service(quiz=_quiz(question_type))
    clock = Mock(side_effect=[1_000_000, 16_000_000])
    monkeypatch.setattr(
        "app.application.quiz_generation.monotonic_ns",
        clock,
    )

    result = service.generate(
        question_type=question_type,
        topic="예금",
    )

    assert result.quiz.question_type == question_type
    assert result.sources[0].chunk_key == "47:0"
    assert result.sources[0].title == "금융 교과서"
    assert result.validation.model_dump() == {
        "schema_valid": True,
        "answer_valid": True,
        "citation_valid": True,
        "grounded": True,
        "duplicate": False,
        "errors": [],
    }
    assert result.execution.model == "gpt-4o-mini"
    assert result.execution.input_tokens == 160
    assert result.execution.output_tokens == 100
    assert result.execution.elapsed_ms == 15
    generation_prompt = model_client.generate_quiz.call_args.args[0]
    assert 'chunk_key="47:4"' in generation_prompt
    assert 'chunk_key="47:5"' not in generation_prompt


def test_stop_before_generation_without_search_result() -> None:
    service, model_client, _ = _service(search_results=[])

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
        )

    assert error.value.errors == ("search_result_required",)
    model_client.generate_quiz.assert_not_called()
    model_client.validate_grounding.assert_not_called()


def test_reject_generated_question_type_different_from_request() -> None:
    service, model_client, _ = _service(quiz=_quiz(QuestionType.SCENARIO))

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
        )

    assert "question_type_mismatch" in error.value.errors
    model_client.validate_grounding.assert_not_called()


@pytest.mark.parametrize(
    ("quiz", "existing_prompts", "expected_error"),
    [
        (
            _quiz(correct_answer={"option_id": "5"}),
            [],
            "correct_answer_not_found",
        ),
        (
            _quiz(
                citations=[
                    {
                        "chunk_key": "47:5",
                        "evidence_text": "금융 교육 근거 5",
                    }
                ]
            ),
            [],
            "citation_chunk_not_found:47:5",
        ),
        (
            _quiz(),
            ["예금에 대한 설명으로 옳은 것은!"],
            "duplicate_prompt",
        ),
    ],
)
def test_reject_code_validation_failure_before_grounding(
    quiz: Quiz,
    existing_prompts: list[str],
    expected_error: str,
) -> None:
    service, model_client, _ = _service(quiz=quiz)

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
            existing_prompts=existing_prompts,
        )

    assert expected_error in error.value.errors
    model_client.validate_grounding.assert_not_called()


def test_reject_unsupported_grounding_result() -> None:
    service, model_client, _ = _service(supported=False)

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
        )

    assert error.value.errors == ("grounding_not_supported",)
    model_client.validate_grounding.assert_called_once()
