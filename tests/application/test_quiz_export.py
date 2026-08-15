from uuid import uuid4

import pytest

from app.application.quiz_export import QuizExportError, to_be_quiz_payload
from app.domain.quiz import (
    Quiz,
    QuizBatchError,
    QuizBatchItemInput,
    QuizBatchRecord,
    QuizBatchStatus,
    QuizExecution,
    QuizGenerationResult,
    QuizSource,
    QuizValidation,
)


def _generation_result(
    question_type: str = "TRUE_FALSE",
    usage_type: str = "SUB_CHAPTER",
) -> QuizGenerationResult:
    if question_type == "TRUE_FALSE":
        options = [
            {"option_id": "O", "text": "O"},
            {"option_id": "X", "text": "X"},
        ]
        correct_answer = {"option_id": "O"}
        scenario_json = None
    else:
        options = [
            {"option_id": "1", "text": "정기 예금에 맡긴다."},
            {"option_id": "2", "text": "주식을 단기 매매한다."},
        ]
        correct_answer = {"option_id": "1"}
        scenario_json = (
            {
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
            if question_type == "SCENARIO"
            else None
        )

    return QuizGenerationResult(
        quiz=Quiz.model_validate(
            {
                "usage_type": usage_type,
                "question_type": question_type,
                "prompt": "정기 예금은 약정 기간 동안 돈을 맡기는 금융상품이다.",
                "scenario_json": scenario_json,
                "options": options,
                "correct_answer": correct_answer,
                "explanation": "정기 예금은 일정 기간 돈을 맡기는 저축성 예금이다.",
                "difficulty": "EASY",
                "citations": [
                    {
                        "chunk_key": "47:0",
                        "evidence_text": "정기 예금은 일정 기간 돈을 맡기는 저축성 예금이다.",
                    }
                ],
            }
        ),
        sources=[
            QuizSource(
                document_id=1,
                chunk_key="47:0",
                title="예금 문서",
                heading=None,
                source_url=None,
                published_at=None,
                evidence_text="정기 예금은 일정 기간 돈을 맡기는 저축성 예금이다.",
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
            model="gpt-4o-mini",
            input_tokens=1,
            output_tokens=1,
            elapsed_ms=1,
        ),
    )


def _succeeded_record(
    *,
    main_chapter_id: int | None = 2,
    sub_chapter_id: int | None = 17,
    question_type: str = "TRUE_FALSE",
    usage_type: str = "SUB_CHAPTER",
) -> QuizBatchRecord:
    return QuizBatchRecord(
        batch_id=uuid4(),
        item_id=uuid4(),
        status=QuizBatchStatus.SUCCEEDED,
        input=QuizBatchItemInput(
            question_type=question_type,
            topic="예금과 적금의 차이",
            main_chapter_id=main_chapter_id,
            sub_chapter_id=sub_chapter_id,
        ),
        result=_generation_result(question_type=question_type, usage_type=usage_type),
        error=None,
        duplicate=None,
    )


def test_to_be_quiz_payload_maps_fields() -> None:
    record = _succeeded_record()

    payload = to_be_quiz_payload(record)

    assert payload == {
        "usage_type": "SUB_CHAPTER",
        "main_chapter_id": 2,
        "sub_chapter_id": 17,
        "question_type": "TRUE_FALSE",
        "difficulty": "EASY",
        "prompt": "정기 예금은 약정 기간 동안 돈을 맡기는 금융상품이다.",
        "scenario_json": None,
        "options_json": [
            {"key": "O", "label": "O"},
            {"key": "X", "label": "X"},
        ],
        "correct_answer_json": {"key": "O"},
        "explanation": "정기 예금은 일정 기간 돈을 맡기는 저축성 예금이다.",
        "source_refs_json": None,
    }


def test_to_be_quiz_payload_rejects_non_succeeded_record() -> None:
    record = QuizBatchRecord(
        batch_id=uuid4(),
        item_id=uuid4(),
        status=QuizBatchStatus.FAILED,
        input=QuizBatchItemInput(
            question_type="TRUE_FALSE",
            topic="예금과 적금의 차이",
            main_chapter_id=2,
            sub_chapter_id=17,
        ),
        result=None,
        error=QuizBatchError(
            stage="quiz_generation",
            errors=["quiz_generation_failed"],
            reason="생성 실패",
            unsupported_claims=[],
        ),
        duplicate=None,
    )

    with pytest.raises(QuizExportError):
        to_be_quiz_payload(record)


def test_to_be_quiz_payload_rejects_missing_main_chapter_id() -> None:
    record = _succeeded_record(main_chapter_id=None, sub_chapter_id=None)

    with pytest.raises(QuizExportError):
        to_be_quiz_payload(record)


def test_to_be_quiz_payload_rejects_scenario_question_type() -> None:
    record = _succeeded_record(
        sub_chapter_id=None,
        question_type="SCENARIO",
        usage_type="MAIN_CHAPTER",
    )

    with pytest.raises(QuizExportError):
        to_be_quiz_payload(record)
