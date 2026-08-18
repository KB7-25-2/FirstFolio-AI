from collections.abc import Iterator, Sequence
from unittest.mock import Mock
from uuid import UUID

import pytest

from app.application.quiz_batch import (
    QuizBatchService,
    build_batch_items_from_targets,
)
from app.application.quiz_generation import (
    QuizGenerationService,
    QuizGenerationValidationError,
)
from app.application.quiz_validation import normalize_quiz_prompt
from app.domain.quiz import (
    ChapterType,
    MainChapterTarget,
    QuestionType,
    Quiz,
    QuizBatchRequestItem,
    QuizBatchStatus,
    QuizExecution,
    QuizGenerationResult,
    QuizGenerationTargets,
    QuizSource,
    QuizValidation,
    SubChapterTarget,
)


def _quiz_result(
    question_type: QuestionType,
    prompt: str,
) -> QuizGenerationResult:
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
            "title": "금융상품 선택",
            "narrative": "저축을 계획하는 학생이 일정한 용돈을 받고 있다.",
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

    return QuizGenerationResult(
        quiz=Quiz.model_validate(
            {
                "usage_type": usage_type,
                "question_type": question_type,
                "prompt": prompt,
                "scenario_json": scenario_json,
                "options": options,
                "correct_answer": correct_answer,
                "explanation": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
                "difficulty": "EASY",
                "citations": [
                    {
                        "chunk_key": "47:0",
                        "evidence_text": (
                            "예금은 금융기관에 돈을 맡기는 금융상품이다."
                        ),
                    }
                ],
            }
        ),
        sources=[
            QuizSource(
                document_id=47,
                chunk_key="47:0",
                title="금융 교과서",
                heading=None,
                source_url=None,
                published_at=None,
                evidence_text="예금은 금융기관에 돈을 맡기는 금융상품이다.",
            )
        ],
        validation=QuizValidation(
            schema_valid=True,
            answer_valid=True,
            citation_valid=True,
            grounded=True,
            duplicate=False,
            errors=[],
        ),
        execution=QuizExecution(
            model="test-model",
            input_tokens=10,
            output_tokens=5,
            elapsed_ms=20,
        ),
    )


def _id_factory() -> Iterator[UUID]:
    for value in range(1, 100):
        yield UUID(int=value)


def _batch_service(generation_service: Mock) -> QuizBatchService:
    ids = _id_factory()
    return QuizBatchService(generation_service, id_factory=lambda: next(ids))


def test_generate_mixed_batch_and_expand_count() -> None:
    generation_service = Mock(spec=QuizGenerationService)
    generation_service.generate.side_effect = [
        _quiz_result(QuestionType.TRUE_FALSE, "OX 질문 1"),
        _quiz_result(QuestionType.TRUE_FALSE, "OX 질문 2"),
        _quiz_result(QuestionType.SINGLE_CHOICE, "4지선다 질문"),
        _quiz_result(QuestionType.SCENARIO, "상황판단 질문"),
    ]
    service = _batch_service(generation_service)

    run = service.generate(
        [
            QuizBatchRequestItem(
                question_type="TRUE_FALSE",
                topic="예금",
                count=2,
            ),
            QuizBatchRequestItem(
                question_type="SINGLE_CHOICE",
                topic="채권",
            ),
            QuizBatchRequestItem(
                question_type="SCENARIO",
                topic="분산 투자",
            ),
        ]
    )

    assert [record.status for record in run.records] == [
        QuizBatchStatus.SUCCEEDED,
        QuizBatchStatus.SUCCEEDED,
        QuizBatchStatus.SUCCEEDED,
        QuizBatchStatus.SUCCEEDED,
    ]
    assert {record.batch_id for record in run.records} == {UUID(int=1)}
    assert len({record.item_id for record in run.records}) == 4
    assert run.summary.model_dump(exclude={"batch_id", "output_path"}) == {
        "total": 4,
        "succeeded": 4,
        "failed": 0,
        "duplicates": 0,
    }
    assert [
        call.kwargs["question_type"]
        for call in generation_service.generate.call_args_list
    ] == [
        QuestionType.TRUE_FALSE,
        QuestionType.TRUE_FALSE,
        QuestionType.SINGLE_CHOICE,
        QuestionType.SCENARIO,
    ]
    assert (
        generation_service.generate.call_args_list[0].kwargs["existing_prompts"] == ()
    )
    assert generation_service.generate.call_args_list[1].kwargs["existing_prompts"] == (
        "OX 질문 1",
    )


def test_continue_after_validation_and_unexpected_failures() -> None:
    generation_service = Mock(spec=QuizGenerationService)
    generation_service.generate.side_effect = [
        QuizGenerationValidationError(
            ["search_result_required"],
            stage="search",
        ),
        RuntimeError("외부 서비스 상세 오류"),
        _quiz_result(QuestionType.TRUE_FALSE, "정상 질문"),
    ]
    service = _batch_service(generation_service)

    run = service.generate(
        [
            QuizBatchRequestItem(question_type="TRUE_FALSE", topic="주제 1"),
            QuizBatchRequestItem(question_type="TRUE_FALSE", topic="주제 2"),
            QuizBatchRequestItem(question_type="TRUE_FALSE", topic="주제 3"),
        ]
    )

    assert [record.status for record in run.records] == [
        QuizBatchStatus.FAILED,
        QuizBatchStatus.FAILED,
        QuizBatchStatus.SUCCEEDED,
    ]
    assert run.records[0].error.errors == ["search_result_required"]
    assert run.records[1].error.errors == ["quiz_generation_failed"]
    assert "외부 서비스 상세 오류" not in run.records[1].error.reason
    assert run.summary.failed == 2
    assert run.summary.succeeded == 1
    assert generation_service.generate.call_count == 3


def test_record_invalid_type_and_blank_topic_without_service_call() -> None:
    generation_service = Mock(spec=QuizGenerationService)
    service = _batch_service(generation_service)

    run = service.generate(
        [
            QuizBatchRequestItem(
                question_type="MULTIPLE_CHOICE",
                topic="예금",
            ),
            QuizBatchRequestItem(
                question_type="TRUE_FALSE",
                topic="   ",
            ),
        ]
    )

    assert [record.error.errors for record in run.records] == [
        ["unsupported_question_type"],
        ["topic_required"],
    ]
    assert all(record.result is None for record in run.records)
    generation_service.generate.assert_not_called()


@pytest.mark.parametrize(
    "duplicate_prompt",
    [
        "예금은 무엇인가?",
        "  예금은...\n무엇인가!  ",
    ],
)
def test_detect_duplicate_prompt_and_link_original_item(
    duplicate_prompt: str,
) -> None:
    generation_service = Mock(spec=QuizGenerationService)
    first_result = _quiz_result(
        QuestionType.SINGLE_CHOICE,
        "예금은 무엇인가?",
    )

    def generate(
        *,
        question_type: QuestionType,
        topic: str,
        existing_prompts: Sequence[str],
    ) -> QuizGenerationResult:
        del topic
        result = (
            first_result
            if not existing_prompts
            else _quiz_result(question_type, duplicate_prompt)
        )
        normalized_existing = {
            normalize_quiz_prompt(prompt) for prompt in existing_prompts
        }

        if normalize_quiz_prompt(result.quiz.prompt) in normalized_existing:
            raise QuizGenerationValidationError(
                ["duplicate_prompt"],
                stage="generation_validation",
                quiz=result.quiz,
            )

        return result

    generation_service.generate.side_effect = generate
    service = _batch_service(generation_service)

    run = service.generate(
        [
            QuizBatchRequestItem(
                question_type="SINGLE_CHOICE",
                topic="예금",
                count=2,
            )
        ]
    )

    first, duplicate = run.records
    assert first.status == QuizBatchStatus.SUCCEEDED
    assert duplicate.status == QuizBatchStatus.DUPLICATE
    assert duplicate.result is None
    assert duplicate.error.errors == ["duplicate_prompt"]
    assert duplicate.duplicate.original_item_id == first.item_id
    assert duplicate.duplicate.prompt == duplicate_prompt
    assert run.summary.duplicates == 1


def test_do_not_mark_different_prompt_as_duplicate() -> None:
    generation_service = Mock(spec=QuizGenerationService)
    generation_service.generate.side_effect = [
        _quiz_result(QuestionType.SINGLE_CHOICE, "예금은 무엇인가?"),
        _quiz_result(QuestionType.SINGLE_CHOICE, "채권은 무엇인가?"),
    ]
    service = _batch_service(generation_service)

    run = service.generate(
        [
            QuizBatchRequestItem(
                question_type="SINGLE_CHOICE",
                topic="금융 상품",
                count=2,
            )
        ]
    )

    assert all(record.status == QuizBatchStatus.SUCCEEDED for record in run.records)
    assert run.summary.duplicates == 0


def test_reject_empty_batch_before_creating_ids() -> None:
    generation_service = Mock(spec=QuizGenerationService)
    id_factory = Mock()
    service = QuizBatchService(generation_service, id_factory=id_factory)

    with pytest.raises(ValueError, match="하나 이상의 항목"):
        service.generate([])

    id_factory.assert_not_called()
    generation_service.generate.assert_not_called()


def test_generate_uuid4_batch_and_item_ids_by_default() -> None:
    generation_service = Mock(spec=QuizGenerationService)
    generation_service.generate.return_value = _quiz_result(
        QuestionType.TRUE_FALSE,
        "예금 OX 질문",
    )
    service = QuizBatchService(generation_service)

    run = service.generate(
        [QuizBatchRequestItem(question_type="TRUE_FALSE", topic="예금")]
    )

    assert run.summary.batch_id.version == 4
    assert run.records[0].batch_id == run.summary.batch_id
    assert run.records[0].item_id.version == 4


def test_generate_carries_chapter_ids_from_request_item_to_record_input() -> None:
    generation_service = Mock(spec=QuizGenerationService)
    generation_service.generate.return_value = _quiz_result(
        QuestionType.TRUE_FALSE,
        "예금 OX 질문",
    )
    service = QuizBatchService(generation_service)

    run = service.generate(
        [
            QuizBatchRequestItem(
                question_type="TRUE_FALSE",
                topic="예금과 적금의 차이",
                main_chapter_id=2,
                sub_chapter_id=17,
            )
        ]
    )

    assert run.records[0].input.main_chapter_id == 2
    assert run.records[0].input.sub_chapter_id == 17


def _targets() -> QuizGenerationTargets:
    return QuizGenerationTargets(
        main_chapters=[
            MainChapterTarget(
                main_chapter_id=2,
                title="예·적금",
                chapter_type=ChapterType.ASSET,
                sub_chapters=[
                    SubChapterTarget(
                        sub_chapter_id=17,
                        main_chapter_id=2,
                        title="예금과 적금의 차이",
                    ),
                    SubChapterTarget(
                        sub_chapter_id=18,
                        main_chapter_id=2,
                        title="금리 이해하기",
                    ),
                ],
            )
        ]
    )


def test_build_batch_items_from_targets_covers_every_sub_chapter_and_type() -> None:
    items = build_batch_items_from_targets(
        _targets(),
        question_types=[QuestionType.TRUE_FALSE, QuestionType.SINGLE_CHOICE],
        count_per_type=3,
    )

    assert len(items) == 4

    first = items[0]
    assert first.question_type == "TRUE_FALSE"
    assert first.topic == "예금과 적금의 차이"
    assert first.main_chapter_id == 2
    assert first.sub_chapter_id == 17
    assert first.count == 3

    second = items[1]
    assert second.question_type == "SINGLE_CHOICE"
    assert second.topic == "예금과 적금의 차이"
    assert second.main_chapter_id == 2
    assert second.sub_chapter_id == 17

    third = items[2]
    assert third.topic == "금리 이해하기"
    assert third.sub_chapter_id == 18


def test_build_batch_items_from_targets_returns_empty_list_when_no_targets() -> None:
    empty_targets = QuizGenerationTargets(main_chapters=[])

    items = build_batch_items_from_targets(
        empty_targets,
        question_types=[QuestionType.TRUE_FALSE],
    )

    assert items == []
