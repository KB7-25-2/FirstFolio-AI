import json
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

import pytest
from pydantic import ValidationError

from app import quiz_batch_dry_run
from app.application.quiz_generation import QuizGenerationService
from app.core.config import Settings
from app.domain.quiz import (
    QuestionType,
    Quiz,
    QuizBatchDuplicate,
    QuizBatchError,
    QuizBatchItemInput,
    QuizBatchRecord,
    QuizBatchStatus,
    QuizExecution,
    QuizGenerationResult,
    QuizSource,
    QuizValidation,
)


def _quiz_result(
    prompt: str = "예금에 대한 설명으로 옳은 것은?",
) -> QuizGenerationResult:
    return QuizGenerationResult(
        quiz=Quiz.model_validate(
            {
                "usage_type": "SUB_CHAPTER",
                "question_type": "SINGLE_CHOICE",
                "prompt": prompt,
                "scenario_json": None,
                "options": [
                    {"option_id": "1", "text": "선택지 1"},
                    {"option_id": "2", "text": "선택지 2"},
                    {"option_id": "3", "text": "선택지 3"},
                    {"option_id": "4", "text": "선택지 4"},
                ],
                "correct_answer": {"option_id": "1"},
                "explanation": "예금은 금융기관에 돈을 맡기는 상품이다.",
                "difficulty": "EASY",
                "citations": [
                    {
                        "chunk_key": "47:0",
                        "evidence_text": "예금은 금융기관에 돈을 맡기는 상품이다.",
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
                evidence_text="예금은 금융기관에 돈을 맡기는 상품이다.",
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


def _write_input(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_run_batch_writes_one_valid_json_object_per_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "batch.json"
    output_path = tmp_path / "result.jsonl"
    _write_input(
        input_path,
        {
            "items": [
                {
                    "question_type": "SINGLE_CHOICE",
                    "topic": "예금",
                    "count": 2,
                }
            ]
        },
    )
    generation_service = Mock(spec=QuizGenerationService)
    generation_service.generate.side_effect = [
        _quiz_result("첫 번째 질문"),
        _quiz_result("두 번째 질문"),
    ]
    create_service = Mock(return_value=generation_service)
    monkeypatch.setattr(
        quiz_batch_dry_run,
        "create_quiz_generation_service",
        create_service,
    )
    settings = Settings(_env_file=None)

    summary = quiz_batch_dry_run.run_quiz_batch_dry_run(
        input_path=input_path,
        output_path=output_path,
        settings=settings,
    )

    lines = output_path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert len(lines) == 2
    assert [record["status"] for record in records] == [
        "SUCCEEDED",
        "SUCCEEDED",
    ]
    assert all(record["result"] is not None for record in records)
    assert all(record["error"] is None for record in records)
    assert summary.total == 2
    assert summary.succeeded == 2
    assert summary.output_path == str(output_path)
    create_service.assert_called_once_with(settings)
    assert [
        call.kwargs["question_type"]
        for call in generation_service.generate.call_args_list
    ] == [
        QuestionType.SINGLE_CHOICE,
        QuestionType.SINGLE_CHOICE,
    ]


def test_write_success_failure_and_duplicate_jsonl_records(
    tmp_path: Path,
) -> None:
    batch_id = UUID(int=1)
    original_item_id = UUID(int=2)
    item_input = QuizBatchItemInput(
        question_type="SINGLE_CHOICE",
        topic="예금",
    )
    failure = QuizBatchError(
        stage="search",
        errors=["search_result_required"],
        reason="검색 결과가 없습니다.",
        unsupported_claims=[],
    )
    records = [
        QuizBatchRecord(
            batch_id=batch_id,
            item_id=original_item_id,
            status=QuizBatchStatus.SUCCEEDED,
            input=item_input,
            result=_quiz_result(),
            error=None,
            duplicate=None,
        ),
        QuizBatchRecord(
            batch_id=batch_id,
            item_id=UUID(int=3),
            status=QuizBatchStatus.FAILED,
            input=item_input,
            result=None,
            error=failure,
            duplicate=None,
        ),
        QuizBatchRecord(
            batch_id=batch_id,
            item_id=UUID(int=4),
            status=QuizBatchStatus.DUPLICATE,
            input=item_input,
            result=None,
            error=QuizBatchError(
                stage="generation_validation",
                errors=["duplicate_prompt"],
                reason="선행 성공 항목과 동일합니다.",
                unsupported_claims=[],
            ),
            duplicate=QuizBatchDuplicate(
                original_item_id=original_item_id,
                prompt="예금에 대한 설명으로 옳은 것은?",
            ),
        ),
    ]
    output_path = tmp_path / "all-statuses.jsonl"

    quiz_batch_dry_run.write_jsonl(output_path, records)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in lines]
    assert len(lines) == 3
    assert [payload["status"] for payload in payloads] == [
        "SUCCEEDED",
        "FAILED",
        "DUPLICATE",
    ]
    assert payloads[0]["result"] is not None
    assert payloads[1]["result"] is None
    assert payloads[1]["error"]["errors"] == ["search_result_required"]
    assert payloads[2]["result"] is None
    assert payloads[2]["duplicate"]["original_item_id"] == str(original_item_id)


def test_reject_empty_input_before_creating_external_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "empty.json"
    _write_input(input_path, {"items": []})
    create_service = Mock()
    monkeypatch.setattr(
        quiz_batch_dry_run,
        "create_quiz_generation_service",
        create_service,
    )

    with pytest.raises(ValidationError):
        quiz_batch_dry_run.run_quiz_batch_dry_run(input_path=input_path)

    create_service.assert_not_called()


def test_reject_existing_output_before_creating_external_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "batch.json"
    output_path = tmp_path / "existing.jsonl"
    _write_input(
        input_path,
        {
            "items": [
                {
                    "question_type": "TRUE_FALSE",
                    "topic": "예금",
                }
            ]
        },
    )
    output_path.write_text("기존 검수 결과\n", encoding="utf-8")
    create_service = Mock()
    monkeypatch.setattr(
        quiz_batch_dry_run,
        "create_quiz_generation_service",
        create_service,
    )

    with pytest.raises(FileExistsError, match="이미 존재"):
        quiz_batch_dry_run.run_quiz_batch_dry_run(
            input_path=input_path,
            output_path=output_path,
        )

    assert output_path.read_text(encoding="utf-8") == "기존 검수 결과\n"
    create_service.assert_not_called()


@pytest.mark.parametrize("invalid_count", [0, -1, True, 1.5])
def test_reject_invalid_count(
    invalid_count: object,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "invalid-count.json"
    _write_input(
        input_path,
        {
            "items": [
                {
                    "question_type": "TRUE_FALSE",
                    "topic": "예금",
                    "count": invalid_count,
                }
            ]
        },
    )

    with pytest.raises(ValidationError):
        quiz_batch_dry_run.load_batch_input(input_path)


def test_main_prints_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "batch.json"
    output_path = tmp_path / "result.jsonl"
    run = Mock()
    run.return_value = quiz_batch_dry_run.QuizBatchSummary(
        batch_id="00000000-0000-0000-0000-000000000001",
        total=3,
        succeeded=1,
        failed=1,
        duplicates=1,
        output_path=str(output_path),
    )
    monkeypatch.setattr(quiz_batch_dry_run, "run_quiz_batch_dry_run", run)

    exit_code = quiz_batch_dry_run.main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "batch_id": "00000000-0000-0000-0000-000000000001",
        "total": 3,
        "succeeded": 1,
        "failed": 1,
        "duplicates": 1,
        "output_path": str(output_path),
    }


def test_main_reports_invalid_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "empty.json"
    _write_input(input_path, {"items": []})
    create_service = Mock()
    monkeypatch.setattr(
        quiz_batch_dry_run,
        "create_quiz_generation_service",
        create_service,
    )

    exit_code = quiz_batch_dry_run.main(["--input", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert json.loads(captured.err)["stage"] == "batch_input"
    create_service.assert_not_called()
