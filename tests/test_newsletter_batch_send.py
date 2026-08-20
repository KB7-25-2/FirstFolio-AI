import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from app import newsletter_batch_send
from app.application.newsletter_generation import NewsletterDraftGenerationError
from app.application.ports.newsletter_model import (
    NewsletterHeadlineModelResult,
    NewsletterIssueModelResult,
)
from app.application.ports.quiz_model import GroundingModelResult
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.newsletter import (
    NewsletterDeliveryResponse,
    NewsletterHeadlineOutput,
    NewsletterIssueGenerationOutput,
)
from app.domain.quiz import GroundingValidation

_MONDAY = date(2026, 8, 17)


def _news_chunk(document_id: str, published_at: datetime) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_key=f"{document_id}:0",
        sequence=0,
        content=f"{document_id} 관련 뉴스 본문",
        title=f"뉴스 {document_id}",
        source=f"{document_id}.txt",
        published_at=published_at,
    )


def _issue_output(document_id: str) -> NewsletterIssueGenerationOutput:
    return NewsletterIssueGenerationOutput.model_validate(
        {
            "title": f"이슈 {document_id}",
            "summary": "요약",
            "financial_word": {"term": "용어", "definition": "정의"},
            "stat": {"label": "라벨", "value": "값"},
            "citations": [
                {"chunk_key": f"{document_id}:0", "evidence_text": "근거 문장"}
            ],
        }
    )


class _FakeModelClient:
    def __init__(self) -> None:
        self.issue_calls = 0

    def generate_issue(self, prompt, citation_candidates):  # noqa: ANN001
        self.issue_calls += 1
        document_id = next(iter(citation_candidates)).split(":")[0]
        return NewsletterIssueModelResult(
            issue=_issue_output(document_id), input_tokens=10, output_tokens=5
        )

    def validate_grounding(self, prompt):  # noqa: ANN001
        return GroundingModelResult(
            validation=GroundingValidation(
                supported=True, reason="근거 확인됨", unsupported_claims=[]
            ),
            input_tokens=3,
            output_tokens=2,
        )

    def generate_headline(self, prompt):  # noqa: ANN001
        return NewsletterHeadlineModelResult(
            headline=NewsletterHeadlineOutput(headline="이번 주 헤드라인"),
            input_tokens=4,
            output_tokens=2,
        )


def _fake_chunk_repository(chunks: list[DocumentChunk]) -> Mock:
    repository = Mock()
    repository.find_all.return_value = chunks
    repository.find_by_chunk_keys.side_effect = lambda keys: [
        chunk for chunk in chunks if chunk.chunk_key in keys
    ]
    return repository


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chunks: list[DocumentChunk],
    api_client: Mock,
) -> None:
    monkeypatch.setattr(
        newsletter_batch_send,
        "MySQLChunkRepository",
        Mock(return_value=_fake_chunk_repository(chunks)),
    )
    monkeypatch.setattr(
        newsletter_batch_send,
        "OpenAINewsletterModelClient",
        Mock(return_value=_FakeModelClient()),
    )
    monkeypatch.setattr(
        newsletter_batch_send,
        "SpringQuizApiClient",
        Mock(return_value=api_client),
    )


def test_run_newsletter_batch_send_generates_and_delivers_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [
        _news_chunk("101", datetime(2026, 8, 17, 9, 0)),
        _news_chunk("102", datetime(2026, 8, 18, 9, 0)),
        _news_chunk("103", datetime(2026, 8, 19, 9, 0)),
    ]
    api_client = Mock()
    api_client.send_newsletter.return_value = NewsletterDeliveryResponse(
        newsletter_id=1, week_start_date=_MONDAY, status="REVIEW"
    )
    _patch_common(monkeypatch, chunks=chunks, api_client=api_client)

    output_path = tmp_path / "draft.jsonl"
    response = newsletter_batch_send.run_newsletter_batch_send(
        week_start_date=_MONDAY,
        settings=Settings(_env_file=None),
        generation_output_path=output_path,
    )

    assert response.newsletter_id == 1
    assert response.status == "REVIEW"
    api_client.send_newsletter.assert_called_once()
    sent_draft = api_client.send_newsletter.call_args.args[0]
    assert len(sent_draft.issues_json) == 3
    assert sent_draft.week_start_date == _MONDAY

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["week_start_date"] == _MONDAY.isoformat()


def test_run_newsletter_batch_send_rejects_too_few_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [_news_chunk("101", datetime(2026, 8, 17, 9, 0))]
    api_client = Mock()
    _patch_common(monkeypatch, chunks=chunks, api_client=api_client)

    with pytest.raises(ValueError, match="이슈 후보가"):
        newsletter_batch_send.run_newsletter_batch_send(
            week_start_date=_MONDAY,
            settings=Settings(_env_file=None),
            generation_output_path=tmp_path / "draft.jsonl",
        )

    api_client.send_newsletter.assert_not_called()


def test_this_monday_resolves_to_start_of_week() -> None:
    assert newsletter_batch_send.this_monday(date(2026, 8, 20)) == date(2026, 8, 17)
    assert newsletter_batch_send.this_monday(date(2026, 8, 17)) == date(2026, 8, 17)
    assert newsletter_batch_send.this_monday(date(2026, 8, 23)) == date(2026, 8, 17)


def test_main_prints_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        newsletter_batch_send,
        "run_newsletter_batch_send",
        Mock(
            return_value=NewsletterDeliveryResponse(
                newsletter_id=1, week_start_date=_MONDAY, status="REVIEW"
            )
        ),
    )

    exit_code = newsletter_batch_send.main(["--week-start-date", "2026-08-17"])

    assert exit_code == 0


def test_main_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        newsletter_batch_send,
        "run_newsletter_batch_send",
        Mock(side_effect=NewsletterDraftGenerationError([])),
    )

    exit_code = newsletter_batch_send.main([])

    assert exit_code == 1


def test_build_argument_parser_parses_week_start_date_and_candidate_count() -> None:
    arguments = newsletter_batch_send.build_argument_parser().parse_args(
        ["--week-start-date", "2026-08-17", "--candidate-count", "7"]
    )

    assert arguments.week_start_date == "2026-08-17"
    assert arguments.candidate_count == 7


def test_build_argument_parser_defaults_candidate_count() -> None:
    arguments = newsletter_batch_send.build_argument_parser().parse_args([])

    assert arguments.week_start_date is None
    assert arguments.candidate_count == newsletter_batch_send._DEFAULT_CANDIDATE_COUNT
