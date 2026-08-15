import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import quiz_batch_send
from app.application.quiz_generation import QuizGenerationService
from app.core.config import Settings
from app.domain.quiz import (
    BeBatchItemResult,
    BeBatchResponse,
    ChapterType,
    MainChapterTarget,
    QuestionType,
    Quiz,
    QuizExecution,
    QuizGenerationResult,
    QuizGenerationTargets,
    QuizSource,
    QuizValidation,
    SubChapterTarget,
)


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
                ],
            )
        ]
    )


def _quiz_result() -> QuizGenerationResult:
    return QuizGenerationResult(
        quiz=Quiz.model_validate(
            {
                "usage_type": "SUB_CHAPTER",
                "question_type": "TRUE_FALSE",
                "prompt": "정기 예금은 약정 기간 동안 돈을 맡기는 금융상품이다.",
                "scenario_json": None,
                "options": [
                    {"option_id": "O", "text": "O"},
                    {"option_id": "X", "text": "X"},
                ],
                "correct_answer": {"option_id": "O"},
                "explanation": "정기 예금은 일정 기간 돈을 맡기는 저축성 예금이다.",
                "difficulty": "EASY",
                "citations": [
                    {"chunk_key": "47:0", "evidence_text": "정기 예금은 ..."}
                ],
            }
        ),
        sources=[
            QuizSource(
                document_id=1,
                chunk_key="47:0",
                title="문서",
                heading=None,
                source_url=None,
                published_at=None,
                evidence_text="정기 예금은 ...",
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
            model="gpt-4o-mini", input_tokens=1, output_tokens=1, elapsed_ms=1
        ),
    )


def _fake_be_response(count: int) -> BeBatchResponse:
    return BeBatchResponse(
        batch_id=uuid4(),
        total=count,
        accepted=count,
        rejected=0,
        items=[
            BeBatchItemResult(
                item_id=uuid4(), result="ACCEPTED", question_id=n, status="REVIEW"
            )
            for n in range(count)
        ],
    )


def test_run_quiz_batch_send_orchestrates_target_lookup_generation_and_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_service = Mock(spec=QuizGenerationService)
    generation_service.generate.return_value = _quiz_result()
    monkeypatch.setattr(
        quiz_batch_send,
        "create_quiz_generation_service",
        Mock(return_value=generation_service),
    )

    fake_api_client = Mock()
    fake_api_client.find_targets.return_value = _targets()
    fake_api_client.send_batch.return_value = _fake_be_response(2)
    monkeypatch.setattr(
        quiz_batch_send,
        "SpringQuizApiClient",
        Mock(return_value=fake_api_client),
    )

    generation_output_path = tmp_path / "generation.jsonl"
    delivery_output_path = tmp_path / "delivery.jsonl"

    responses = quiz_batch_send.run_quiz_batch_send(
        question_types=[QuestionType.TRUE_FALSE],
        count_per_type=2,
        settings=Settings(_env_file=None),
        generation_output_path=generation_output_path,
        delivery_output_path=delivery_output_path,
    )

    fake_api_client.find_targets.assert_called_once()
    assert generation_service.generate.call_count == 2
    fake_api_client.send_batch.assert_called_once()

    assert len(responses) == 1
    assert responses[0].accepted == 2

    generation_lines = generation_output_path.read_text(encoding="utf-8").splitlines()
    assert len(generation_lines) == 2
    assert all(json.loads(line)["status"] == "SUCCEEDED" for line in generation_lines)

    delivery_lines = delivery_output_path.read_text(encoding="utf-8").splitlines()
    assert len(delivery_lines) == 1
    assert json.loads(delivery_lines[0])["accepted"] == 2


def test_run_quiz_batch_send_rejects_empty_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        quiz_batch_send,
        "create_quiz_generation_service",
        Mock(return_value=Mock(spec=QuizGenerationService)),
    )

    fake_api_client = Mock()
    fake_api_client.find_targets.return_value = QuizGenerationTargets(main_chapters=[])
    monkeypatch.setattr(
        quiz_batch_send,
        "SpringQuizApiClient",
        Mock(return_value=fake_api_client),
    )

    with pytest.raises(ValueError, match="생성 대상 단원이 없습니다"):
        quiz_batch_send.run_quiz_batch_send(
            settings=Settings(_env_file=None),
            generation_output_path=tmp_path / "generation.jsonl",
            delivery_output_path=tmp_path / "delivery.jsonl",
        )

    fake_api_client.send_batch.assert_not_called()


def test_main_prints_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        quiz_batch_send,
        "run_quiz_batch_send",
        Mock(return_value=[_fake_be_response(2)]),
    )

    exit_code = quiz_batch_send.main(["--count-per-type", "2"])

    assert exit_code == 0


def test_main_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        quiz_batch_send,
        "run_quiz_batch_send",
        Mock(side_effect=ValueError("생성 대상 단원이 없습니다.")),
    )

    exit_code = quiz_batch_send.main([])

    assert exit_code == 1


def test_build_argument_parser_splits_question_types() -> None:
    arguments = quiz_batch_send.build_argument_parser().parse_args(
        ["--question-types", "TRUE_FALSE,SINGLE_CHOICE", "--count-per-type", "5"]
    )

    assert arguments.question_types == "TRUE_FALSE,SINGLE_CHOICE"
    assert arguments.count_per_type == 5
