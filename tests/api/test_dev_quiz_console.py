from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dev_quiz_console import (
    _BatchGroup,
    _format_duration,
    _read_history,
    get_quiz_batch_service,
)
from app.application.quiz_batch import QuizBatchRun, QuizBatchService
from app.domain.quiz import (
    QuizBatchError,
    QuizBatchItemInput,
    QuizBatchRecord,
    QuizBatchStatus,
    QuizBatchSummary,
    QuizGenerationResult,
)
from app.main import app


def _quiz_generation_result() -> QuizGenerationResult:
    return QuizGenerationResult.model_validate(
        {
            "quiz": {
                "usage_type": "SUB_CHAPTER",
                "question_type": "SINGLE_CHOICE",
                "prompt": "예금에 대한 설명으로 옳은 것은?",
                "scenario_json": None,
                "options": [
                    {"option_id": "1", "text": "선택지 1"},
                    {"option_id": "2", "text": "선택지 2"},
                ],
                "correct_answer": {"option_id": "1"},
                "explanation": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
                "difficulty": "EASY",
                "citations": [
                    {"chunk_key": "81:10", "evidence_text": "예금은 금융상품이다."}
                ],
            },
            "sources": [
                {
                    "document_id": 81,
                    "chunk_key": "81:10",
                    "title": "금융 교과서",
                    "heading": "저축상품",
                    "source_url": None,
                    "published_at": None,
                    "evidence_text": "예금은 금융상품이다.",
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


def _succeeded_record(
    topic: str = "예금의 특징",
    question_type: str = "SINGLE_CHOICE",
) -> QuizBatchRecord:
    return QuizBatchRecord(
        batch_id=uuid4(),
        item_id=uuid4(),
        status=QuizBatchStatus.SUCCEEDED,
        input=QuizBatchItemInput(question_type=question_type, topic=topic),
        result=_quiz_generation_result(),
        error=None,
        duplicate=None,
    )


def _failed_record(reason: str = "지원하지 않는 문제 유형입니다.") -> QuizBatchRecord:
    return QuizBatchRecord(
        batch_id=uuid4(),
        item_id=uuid4(),
        status=QuizBatchStatus.FAILED,
        input=QuizBatchItemInput(question_type="MULTIPLE_CHOICE", topic="예금"),
        result=None,
        error=QuizBatchError(
            stage="input_validation",
            errors=["unsupported_question_type"],
            reason=reason,
            unsupported_claims=[],
        ),
        duplicate=None,
    )


def test_read_history_returns_empty_list_for_missing_directory(tmp_path: Path) -> None:
    assert _read_history(tmp_path / "missing") == []


def test_read_history_parses_and_sorts_by_mtime(tmp_path: Path) -> None:
    older = tmp_path / "older.jsonl"
    newer = tmp_path / "newer.jsonl"
    older.write_text(_succeeded_record("오래된 항목").model_dump_json() + "\n")
    newer.write_text(_succeeded_record("최근 항목").model_dump_json() + "\n")

    import os
    import time

    older_time = time.time() - 100
    os.utime(older, (older_time, older_time))

    groups = _read_history(tmp_path)

    assert isinstance(groups[0], _BatchGroup)
    assert [g.records[0].input.topic for g in groups] == ["최근 항목", "오래된 항목"]


def test_read_history_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "batch.jsonl"
    path.write_text(
        _succeeded_record().model_dump_json() + "\n\n",
    )

    groups = _read_history(tmp_path)

    assert len(groups) == 1
    assert len(groups[0].records) == 1


def test_format_duration_under_a_minute() -> None:
    assert _format_duration(45_000) == "45초"


def test_format_duration_over_a_minute() -> None:
    assert _format_duration(222_000) == "3분 42초"


@pytest.fixture
def quiz_batch_service() -> Mock:
    return Mock(spec=QuizBatchService)


@pytest.fixture
def client(quiz_batch_service: Mock) -> Iterator[TestClient]:
    app.dependency_overrides[get_quiz_batch_service] = lambda: quiz_batch_service

    try:
        with TestClient(app, follow_redirects=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_quiz_batch_service, None)


def test_render_quiz_console_shows_empty_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.api.dev_quiz_console._HISTORY_DIRECTORY",
        tmp_path / "empty",
    )

    response = client.get("/api/v1/dev/quiz-console")

    assert response.status_code == 200
    assert "아직 생성한 문제가 없습니다." in response.text
    assert "문제 생성" in response.text


def test_render_quiz_console_escapes_topic(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_directory = tmp_path / "history"
    history_directory.mkdir()
    record = _succeeded_record(topic="<script>alert(1)</script>")
    (history_directory / "batch.jsonl").write_text(record.model_dump_json() + "\n")
    monkeypatch.setattr(
        "app.api.dev_quiz_console._HISTORY_DIRECTORY",
        history_directory,
    )

    response = client.get("/api/v1/dev/quiz-console")

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_render_quiz_console_shows_metrics_and_status_badges(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_directory = tmp_path / "history"
    history_directory.mkdir()
    lines = [
        _succeeded_record().model_dump_json(),
        _failed_record().model_dump_json(),
    ]
    (history_directory / "batch.jsonl").write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(
        "app.api.dev_quiz_console._HISTORY_DIRECTORY",
        history_directory,
    )

    response = client.get("/api/v1/dev/quiz-console")

    assert response.status_code == 200
    assert "성공" in response.text
    assert "실패" in response.text
    assert "지원하지 않는 문제 유형입니다." in response.text


def test_render_quiz_console_includes_per_batch_filter_toggle(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_directory = tmp_path / "history"
    history_directory.mkdir()
    record_a = _succeeded_record(topic="채권", question_type="TRUE_FALSE")
    record_b = _succeeded_record(topic="주식", question_type="SINGLE_CHOICE")
    lines = [record_a.model_dump_json(), record_b.model_dump_json()]
    (history_directory / "batch.jsonl").write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(
        "app.api.dev_quiz_console._HISTORY_DIRECTORY",
        history_directory,
    )
    batch_id = str(record_a.batch_id)

    response = client.get("/api/v1/dev/quiz-console")

    assert response.status_code == 200
    assert f'id="qtype-{batch_id}"' in response.text
    assert f'id="topic-{batch_id}"' in response.text
    assert f'id="items-{batch_id}"' in response.text
    assert 'data-question-type="TRUE_FALSE" data-topic="채권"' in response.text
    assert 'data-question-type="SINGLE_CHOICE" data-topic="주식"' in response.text
    assert "function filterBatchItems" in response.text


def test_generate_from_console_writes_history_and_redirects(
    client: TestClient,
    quiz_batch_service: Mock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_directory = tmp_path / "generated"
    monkeypatch.setattr(
        "app.api.dev_quiz_console._HISTORY_DIRECTORY",
        history_directory,
    )
    record = _succeeded_record(topic="정기 예금의 특징")
    quiz_batch_service.generate.return_value = QuizBatchRun(
        records=(record,),
        summary=QuizBatchSummary(
            batch_id=record.batch_id,
            total=1,
            succeeded=1,
            failed=0,
            duplicates=0,
        ),
    )

    response = client.get(
        "/api/v1/dev/quiz-console/generate",
        params={"question_type": "SINGLE_CHOICE", "topic": "정기 예금의 특징"},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/api/v1/dev/quiz-console"
    written_files = list(history_directory.glob("*.jsonl"))
    assert len(written_files) == 1
    assert "정기 예금의 특징" in written_files[0].read_text(encoding="utf-8")
    quiz_batch_service.generate.assert_called_once()
    called_items = quiz_batch_service.generate.call_args.args[0]
    assert len(called_items) == 1
    assert called_items[0].question_type == "SINGLE_CHOICE"
    assert called_items[0].topic == "정기 예금의 특징"
    assert called_items[0].count == 1
