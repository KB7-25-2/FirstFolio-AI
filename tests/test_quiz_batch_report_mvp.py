import json
from pathlib import Path
from uuid import uuid4

import pytest

from app import quiz_batch_report_mvp
from app.domain.quiz import QuizBatchRecord

_BATCH_ID = str(uuid4())


def _succeeded_record(
    *,
    topic: str,
    chunk_key: str,
    item_id: str | None = None,
) -> dict[str, object]:
    return {
        "batch_id": _BATCH_ID,
        "item_id": item_id or str(uuid4()),
        "status": "SUCCEEDED",
        "input": {"question_type": "SINGLE_CHOICE", "topic": topic},
        "result": {
            "quiz": {
                "usage_type": "SUB_CHAPTER",
                "question_type": "SINGLE_CHOICE",
                "prompt": f"{topic} 문항 {chunk_key}",
                "scenario_json": None,
                "options": [
                    {"option_id": "1", "text": "선택지 1"},
                    {"option_id": "2", "text": "선택지 2"},
                    {"option_id": "3", "text": "선택지 3"},
                    {"option_id": "4", "text": "선택지 4"},
                ],
                "correct_answer": {"option_id": "1"},
                "explanation": "해설",
                "difficulty": "EASY",
                "citations": [
                    {"chunk_key": chunk_key, "evidence_text": "근거 문장"},
                ],
            },
            "sources": [
                {
                    "document_id": int(chunk_key.split(":")[0]),
                    "chunk_key": chunk_key,
                    "title": "금융 교과서",
                    "heading": None,
                    "source_url": None,
                    "published_at": None,
                    "evidence_text": "근거 문장",
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
                "input_tokens": 100,
                "output_tokens": 50,
                "elapsed_ms": 10,
            },
        },
        "error": None,
        "duplicate": None,
    }


def _failed_record(
    *,
    topic: str,
    stage: str,
    errors: list[str],
) -> dict[str, object]:
    return {
        "batch_id": _BATCH_ID,
        "item_id": str(uuid4()),
        "status": "FAILED",
        "input": {"question_type": "SINGLE_CHOICE", "topic": topic},
        "result": None,
        "error": {
            "stage": stage,
            "errors": errors,
            "reason": "실패 사유",
            "unsupported_claims": [],
        },
        "duplicate": None,
    }


def _duplicate_record(
    *,
    topic: str,
    original_item_id: str,
    error_code: str,
    prompt: str = "중복 문항",
) -> dict[str, object]:
    return {
        "batch_id": _BATCH_ID,
        "item_id": str(uuid4()),
        "status": "DUPLICATE",
        "input": {"question_type": "SINGLE_CHOICE", "topic": topic},
        "result": None,
        "error": {
            "stage": "generation_validation",
            "errors": [error_code],
            "reason": "중복 문항입니다.",
            "unsupported_claims": [],
        },
        "duplicate": {"original_item_id": original_item_id, "prompt": prompt},
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )


def test_load_batch_records_parses_each_line(tmp_path: Path) -> None:
    path = tmp_path / "batch.jsonl"
    _write_jsonl(
        path,
        [
            _succeeded_record(topic="예금", chunk_key="47:0"),
            _failed_record(
                topic="예금", stage="search", errors=["search_result_required"]
            ),
        ],
    )

    records = quiz_batch_report_mvp.load_batch_records(path)

    assert len(records) == 2
    assert all(isinstance(record, QuizBatchRecord) for record in records)


def test_load_batch_records_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="찾을 수 없습니다"):
        quiz_batch_report_mvp.load_batch_records(tmp_path / "missing.jsonl")


def test_load_batch_records_raises_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="레코드가 없습니다"):
        quiz_batch_report_mvp.load_batch_records(path)


def test_summarize_batch_computes_success_and_failure_counts() -> None:
    records = [
        QuizBatchRecord.model_validate(
            _succeeded_record(topic="예금", chunk_key="47:0")
        ),
        QuizBatchRecord.model_validate(
            _failed_record(
                topic="예금",
                stage="grounding_validation",
                errors=["grounding_not_supported"],
            )
        ),
        QuizBatchRecord.model_validate(
            _failed_record(
                topic="예금",
                stage="search",
                errors=["search_result_required"],
            )
        ),
    ]

    summary = quiz_batch_report_mvp.summarize_batch(records)

    assert summary["total"] == 3
    assert summary["succeeded"] == 1
    assert summary["failed"] == 2
    assert summary["duplicates"] == 0
    assert summary["success_rate"] == pytest.approx(round(1 / 3, 4))
    assert summary["failure_by_stage"] == {
        "grounding_validation": 1,
        "search": 1,
    }
    assert summary["failure_by_error_code"] == {
        "grounding_not_supported": 1,
        "search_result_required": 1,
    }
    assert summary["grounding_not_supported_count"] == 1
    assert summary["grounding_not_supported_rate"] == pytest.approx(round(1 / 3, 4))


def test_summarize_batch_splits_exact_and_semantic_duplicates() -> None:
    original_item_id = str(uuid4())
    records = [
        QuizBatchRecord.model_validate(
            _succeeded_record(topic="예금", chunk_key="47:0")
        ),
        QuizBatchRecord.model_validate(
            _duplicate_record(
                topic="예금",
                original_item_id=original_item_id,
                error_code="duplicate_prompt",
            )
        ),
        QuizBatchRecord.model_validate(
            _duplicate_record(
                topic="예금",
                original_item_id=original_item_id,
                error_code="semantic_duplicate_prompt",
            )
        ),
    ]

    summary = quiz_batch_report_mvp.summarize_batch(records)

    assert summary["duplicates"] == 2
    assert summary["duplicate_exact_count"] == 1
    assert summary["duplicate_semantic_count"] == 1


def test_summarize_batch_measures_evidence_diversity_per_topic() -> None:
    records = [
        QuizBatchRecord.model_validate(
            _succeeded_record(topic="예금", chunk_key="47:0")
        ),
        QuizBatchRecord.model_validate(
            _succeeded_record(topic="예금", chunk_key="47:0")
        ),
        QuizBatchRecord.model_validate(
            _succeeded_record(topic="예금", chunk_key="47:1")
        ),
        QuizBatchRecord.model_validate(
            _succeeded_record(topic="채권", chunk_key="48:0")
        ),
    ]

    summary = quiz_batch_report_mvp.summarize_batch(records)

    assert summary["evidence_diversity_by_topic"] == {
        "예금": {
            "succeeded_count": 3,
            "citations_total": 3,
            "distinct_chunk_keys": 2,
        },
        "채권": {
            "succeeded_count": 1,
            "citations_total": 1,
            "distinct_chunk_keys": 1,
        },
    }


def test_summarize_batch_handles_empty_records_without_division_error() -> None:
    summary = quiz_batch_report_mvp.summarize_batch([])

    assert summary["total"] == 0
    assert summary["success_rate"] == 0.0
    assert summary["grounding_not_supported_rate"] == 0.0


def test_build_report_includes_baseline_when_given(tmp_path: Path) -> None:
    input_path = tmp_path / "current.jsonl"
    baseline_path = tmp_path / "baseline.jsonl"
    _write_jsonl(input_path, [_succeeded_record(topic="예금", chunk_key="47:0")])
    _write_jsonl(baseline_path, [_succeeded_record(topic="예금", chunk_key="47:1")])

    report = quiz_batch_report_mvp.build_report(
        input_path=input_path,
        baseline_path=baseline_path,
    )

    assert report["input_path"] == str(input_path)
    assert report["baseline_path"] == str(baseline_path)
    assert report["current"]["total"] == 1
    assert report["baseline"]["total"] == 1


def test_build_report_omits_baseline_when_not_given(tmp_path: Path) -> None:
    input_path = tmp_path / "current.jsonl"
    _write_jsonl(input_path, [_succeeded_record(topic="예금", chunk_key="47:0")])

    report = quiz_batch_report_mvp.build_report(input_path=input_path)

    assert "baseline" not in report
    assert "baseline_path" not in report


def test_write_report_creates_parent_directories(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "report.json"

    quiz_batch_report_mvp.write_report(output_path, {"total": 1})

    assert json.loads(output_path.read_text(encoding="utf-8")) == {"total": 1}


def test_default_output_path_uses_evaluation_directory() -> None:
    output_path = quiz_batch_report_mvp.default_output_path()

    assert output_path.parent == Path("data/local/evaluation")
    assert output_path.name.startswith("quiz_batch_report_")
    assert output_path.suffix == ".json"


def test_main_prints_report_and_writes_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "current.jsonl"
    output_path = tmp_path / "report.json"
    _write_jsonl(input_path, [_succeeded_record(topic="예금", chunk_key="47:0")])

    exit_code = quiz_batch_report_mvp.main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    printed = json.loads(captured.out)
    assert printed["output_path"] == str(output_path)
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["current"]["total"] == 1


def test_main_prints_error_and_returns_failure_for_missing_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = quiz_batch_report_mvp.main(["--input", "/no/such/file.jsonl"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "찾을 수 없습니다" in json.loads(captured.err)["error"]
