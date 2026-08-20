from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.newsletter import (
    FinancialWord,
    NewsletterDraft,
    NewsletterIssue,
    NewsletterIssueSource,
    NewsletterStat,
)


def _financial_words(count: int = 3) -> list[dict[str, str]]:
    return [{"term": f"용어{i}", "definition": f"정의{i}"} for i in range(count)]


def _issues(count: int = 3) -> list[dict[str, object]]:
    return [
        {
            "title": f"이슈{i}",
            "summary": f"요약{i}",
            "related_term": "용어0",
            "sources": [
                {
                    "document_id": 1,
                    "chunk_key": f"1:{i}",
                    "source_url": "https://example.com",
                    "evidence_text": "근거 문장",
                }
            ],
        }
        for i in range(count)
    ]


def _stats(count: int = 3) -> list[dict[str, str]]:
    return [{"label": f"라벨{i}", "value": f"값{i}"} for i in range(count)]


def _draft(**overrides: object) -> dict[str, object]:
    payload = {
        "week_start_date": date(2026, 8, 17),
        "headline": "대제목",
        "financial_words_json": _financial_words(),
        "issues_json": _issues(),
        "stats_json": _stats(),
    }
    payload.update(overrides)
    return payload


def test_newsletter_draft_accepts_exactly_three_sections() -> None:
    draft = NewsletterDraft.model_validate(_draft())

    assert len(draft.financial_words_json) == 3
    assert len(draft.issues_json) == 3
    assert len(draft.stats_json) == 3


@pytest.mark.parametrize(
    "field",
    ["financial_words_json", "issues_json", "stats_json"],
)
def test_newsletter_draft_rejects_two_items(field: str) -> None:
    builders = {
        "financial_words_json": _financial_words,
        "issues_json": _issues,
        "stats_json": _stats,
    }
    with pytest.raises(ValidationError):
        NewsletterDraft.model_validate(_draft(**{field: builders[field](2)}))


@pytest.mark.parametrize(
    "field",
    ["financial_words_json", "issues_json", "stats_json"],
)
def test_newsletter_draft_rejects_four_items(field: str) -> None:
    builders = {
        "financial_words_json": _financial_words,
        "issues_json": _issues,
        "stats_json": _stats,
    }
    with pytest.raises(ValidationError):
        NewsletterDraft.model_validate(_draft(**{field: builders[field](4)}))


def test_newsletter_issue_requires_at_least_one_source() -> None:
    with pytest.raises(ValidationError):
        NewsletterIssue.model_validate(
            {
                "title": "이슈",
                "summary": "요약",
                "related_term": "용어",
                "sources": [],
            }
        )


def test_newsletter_draft_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        NewsletterDraft.model_validate(_draft(extra_field="안됨"))


def test_financial_word_rejects_blank_term() -> None:
    with pytest.raises(ValidationError):
        FinancialWord.model_validate({"term": "", "definition": "정의"})


def test_newsletter_issue_source_allows_null_source_url() -> None:
    source = NewsletterIssueSource.model_validate(
        {
            "document_id": 1,
            "chunk_key": "1:0",
            "source_url": None,
            "evidence_text": "근거",
        }
    )

    assert source.source_url is None


def test_newsletter_stat_rejects_blank_value() -> None:
    with pytest.raises(ValidationError):
        NewsletterStat.model_validate({"label": "라벨", "value": ""})
