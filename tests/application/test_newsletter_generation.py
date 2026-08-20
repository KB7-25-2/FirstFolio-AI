from datetime import date, datetime
from unittest.mock import Mock

import pytest

from app.application.newsletter_collection import NewsletterIssueCandidate
from app.application.newsletter_generation import (
    NewsletterDraftGenerationError,
    NewsletterGenerationService,
    NewsletterIssueGenerationError,
    generate_newsletter_draft,
)
from app.application.ports.newsletter_model import (
    NewsletterHeadlineModelResult,
    NewsletterIssueModelResult,
)
from app.application.ports.quiz_model import GroundingModelResult
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.newsletter import (
    NewsletterHeadlineOutput,
    NewsletterIssue,
    NewsletterIssueGenerationOutput,
    NewsletterIssueSource,
)
from app.domain.quiz import GroundingValidation


def _settings() -> Settings:
    return Settings(_env_file=None)


def _chunk(chunk_key: str = "47:0") -> DocumentChunk:
    return DocumentChunk(
        document_id="47",
        chunk_key=chunk_key,
        sequence=0,
        content="정기예금 잔액이 크게 늘었다.",
        title="정기예금 급증",
        source="news.txt",
    )


def _candidate(
    document_id: str = "47", title: str = "정기예금 급증"
) -> NewsletterIssueCandidate:
    return NewsletterIssueCandidate(
        document_id=document_id,
        title=title,
        published_at=datetime(2026, 8, 17, 9, 0),
        chunks=(_chunk(f"{document_id}:0"),),
    )


def _issue_output(chunk_key: str = "47:0") -> NewsletterIssueGenerationOutput:
    return NewsletterIssueGenerationOutput.model_validate(
        {
            "title": "정기예금 급증",
            "summary": "기업 자금이 정기예금으로 몰렸다.",
            "financial_word": {
                "term": "정기예금",
                "definition": "일정 기간 돈을 맡기는 예금",
            },
            "stat": {"label": "정기예금 증가액", "value": "+35조 5,401억 원"},
            "citations": [
                {
                    "chunk_key": chunk_key,
                    "evidence_text": "정기예금 잔액이 크게 늘었다.",
                }
            ],
        }
    )


def _grounding_result(supported: bool = True) -> GroundingModelResult:
    return GroundingModelResult(
        validation=GroundingValidation(
            supported=supported,
            reason="검증 결과",
            unsupported_claims=[] if supported else ["근거 없는 주장"],
        ),
        input_tokens=10,
        output_tokens=5,
    )


def _headline_result() -> NewsletterHeadlineModelResult:
    return NewsletterHeadlineModelResult(
        headline=NewsletterHeadlineOutput(headline="이번 주 헤드라인"),
        input_tokens=8,
        output_tokens=4,
    )


class _FakeModelClient:
    def __init__(self) -> None:
        self.issue_queue: list[NewsletterIssueGenerationOutput | Exception] = []
        self.grounding_queue: list[GroundingModelResult] = []
        self.headline_result: NewsletterHeadlineModelResult = _headline_result()
        self.generate_issue_calls = 0

    def generate_issue(self, prompt, citation_candidates):  # noqa: ANN001
        self.generate_issue_calls += 1
        outcome = self.issue_queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return NewsletterIssueModelResult(
            issue=outcome, input_tokens=20, output_tokens=10
        )

    def validate_grounding(self, prompt):  # noqa: ANN001
        return self.grounding_queue.pop(0)

    def generate_headline(self, prompt):  # noqa: ANN001
        return self.headline_result


def _chunk_repository_returning(chunk: DocumentChunk) -> Mock:
    repository = Mock()
    repository.find_by_chunk_keys.return_value = [chunk]
    return repository


def test_generate_issue_succeeds_and_sums_tokens() -> None:
    model_client = _FakeModelClient()
    model_client.issue_queue = [_issue_output()]
    model_client.grounding_queue = [_grounding_result(supported=True)]
    service = NewsletterGenerationService(
        settings=_settings(),
        chunk_repository=_chunk_repository_returning(_chunk()),
        model_client=model_client,
    )

    result = service.generate_issue(_candidate())

    assert result.issue.title == "정기예금 급증"
    assert result.issue.related_term == "정기예금"
    assert len(result.issue.sources) == 1
    assert result.financial_word.term == "정기예금"
    assert result.input_tokens == 30
    assert result.output_tokens == 15


def test_generate_issue_raises_when_grounding_not_supported() -> None:
    model_client = _FakeModelClient()
    model_client.issue_queue = [_issue_output()]
    model_client.grounding_queue = [_grounding_result(supported=False)]
    service = NewsletterGenerationService(
        settings=_settings(),
        chunk_repository=_chunk_repository_returning(_chunk()),
        model_client=model_client,
    )

    with pytest.raises(NewsletterIssueGenerationError) as excinfo:
        service.generate_issue(_candidate())

    assert excinfo.value.stage == "grounding_validation"
    assert excinfo.value.unsupported_claims == ("근거 없는 주장",)


def test_generate_issue_raises_when_sources_unresolved() -> None:
    model_client = _FakeModelClient()
    model_client.issue_queue = [_issue_output()]
    model_client.grounding_queue = [_grounding_result(supported=True)]
    empty_repository = Mock()
    empty_repository.find_by_chunk_keys.return_value = []
    service = NewsletterGenerationService(
        settings=_settings(),
        chunk_repository=empty_repository,
        model_client=model_client,
    )

    with pytest.raises(NewsletterIssueGenerationError) as excinfo:
        service.generate_issue(_candidate())

    assert excinfo.value.stage == "source_resolution"


def test_generate_headline_returns_text_and_tokens() -> None:
    model_client = _FakeModelClient()
    service = NewsletterGenerationService(
        settings=_settings(),
        chunk_repository=Mock(),
        model_client=model_client,
    )

    headline, input_tokens, output_tokens = service.generate_headline([_issue()])

    assert headline == "이번 주 헤드라인"
    assert input_tokens == 8
    assert output_tokens == 4


def _issue() -> NewsletterIssue:
    return NewsletterIssue(
        title="정기예금 급증",
        summary="기업 자금이 정기예금으로 몰렸다.",
        related_term="정기예금",
        sources=[
            NewsletterIssueSource(
                document_id=47, chunk_key="47:0", source_url=None, evidence_text="근거"
            )
        ],
    )


def test_generate_newsletter_draft_builds_draft_from_three_successes() -> None:
    model_client = _FakeModelClient()
    model_client.issue_queue = [
        _issue_output("101:0"),
        _issue_output("102:0"),
        _issue_output("103:0"),
    ]
    model_client.grounding_queue = [
        _grounding_result(True),
        _grounding_result(True),
        _grounding_result(True),
    ]
    repository = Mock()
    repository.find_by_chunk_keys.side_effect = lambda keys: [_chunk(keys[0])]
    service = NewsletterGenerationService(
        settings=_settings(), chunk_repository=repository, model_client=model_client
    )
    candidates = [_candidate("101"), _candidate("102"), _candidate("103")]

    result = generate_newsletter_draft(service, candidates, date(2026, 8, 17))

    assert result.draft.week_start_date == date(2026, 8, 17)
    assert result.draft.headline == "이번 주 헤드라인"
    assert len(result.draft.issues_json) == 3
    assert len(result.draft.financial_words_json) == 3
    assert len(result.draft.stats_json) == 3
    assert result.skipped_candidates == ()
    assert model_client.generate_issue_calls == 3


def test_generate_newsletter_draft_skips_failed_candidate_and_uses_next() -> None:
    model_client = _FakeModelClient()
    model_client.issue_queue = [
        _issue_output("101:0"),
        _issue_output("102:0"),
        _issue_output("103:0"),
        _issue_output("104:0"),
    ]
    model_client.grounding_queue = [
        _grounding_result(False),  # 101 fails
        _grounding_result(True),  # 102 succeeds
        _grounding_result(True),  # 103 succeeds
        _grounding_result(True),  # 104 succeeds
    ]
    repository = Mock()
    repository.find_by_chunk_keys.side_effect = lambda keys: [_chunk(keys[0])]
    service = NewsletterGenerationService(
        settings=_settings(), chunk_repository=repository, model_client=model_client
    )
    candidates = [
        _candidate("101"),
        _candidate("102"),
        _candidate("103"),
        _candidate("104"),
    ]

    result = generate_newsletter_draft(service, candidates, date(2026, 8, 17))

    assert len(result.draft.issues_json) == 3
    assert len(result.skipped_candidates) == 1
    assert result.skipped_candidates[0].document_id == "101"
    assert model_client.generate_issue_calls == 4


def test_generate_newsletter_draft_raises_when_not_enough_succeed() -> None:
    model_client = _FakeModelClient()
    model_client.issue_queue = [_issue_output("101:0"), _issue_output("102:0")]
    model_client.grounding_queue = [_grounding_result(False), _grounding_result(False)]
    repository = Mock()
    repository.find_by_chunk_keys.side_effect = lambda keys: [_chunk(keys[0])]
    service = NewsletterGenerationService(
        settings=_settings(), chunk_repository=repository, model_client=model_client
    )
    candidates = [_candidate("101"), _candidate("102")]

    with pytest.raises(NewsletterDraftGenerationError) as excinfo:
        generate_newsletter_draft(service, candidates, date(2026, 8, 17))

    assert len(excinfo.value.failures) == 2


def test_generate_newsletter_draft_stops_once_three_succeed() -> None:
    model_client = _FakeModelClient()
    model_client.issue_queue = [
        _issue_output("101:0"),
        _issue_output("102:0"),
        _issue_output("103:0"),
    ]
    model_client.grounding_queue = [
        _grounding_result(True),
        _grounding_result(True),
        _grounding_result(True),
    ]
    repository = Mock()
    repository.find_by_chunk_keys.side_effect = lambda keys: [_chunk(keys[0])]
    service = NewsletterGenerationService(
        settings=_settings(), chunk_repository=repository, model_client=model_client
    )
    candidates = [
        _candidate("101"),
        _candidate("102"),
        _candidate("103"),
        _candidate("104"),
        _candidate("105"),
    ]

    result = generate_newsletter_draft(service, candidates, date(2026, 8, 17))

    assert len(result.draft.issues_json) == 3
    assert model_client.generate_issue_calls == 3
