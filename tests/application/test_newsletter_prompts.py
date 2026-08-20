import pytest

from app.application.newsletter_prompts import (
    build_newsletter_grounding_validation_prompt,
    build_newsletter_headline_prompt,
    build_newsletter_issue_generation_prompt,
)
from app.domain.chunk import DocumentChunk
from app.domain.newsletter import (
    NewsletterIssue,
    NewsletterIssueGenerationOutput,
    NewsletterIssueSource,
)


def _chunks(count: int = 3) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            document_id="47",
            chunk_key=f"47:{index}",
            sequence=index,
            content=f"금융 근거 본문 {index}",
            title="금융 뉴스",
            source="news.txt",
        )
        for index in range(count)
    ]


def _issue_output() -> NewsletterIssueGenerationOutput:
    return NewsletterIssueGenerationOutput.model_validate(
        {
            "title": "정기예금 급증",
            "summary": "기업 자금이 정기예금으로 몰렸다.",
            "financial_word": {
                "term": "정기예금",
                "definition": "일정 기간 돈을 맡기는 예금",
            },
            "stat": {"label": "정기예금 증가액", "value": "+35조 5,401억 원"},
            "citations": [{"chunk_key": "47:0", "evidence_text": "금융 근거 본문 0"}],
        }
    )


def _issue() -> NewsletterIssue:
    return NewsletterIssue(
        title="정기예금 급증",
        summary="기업 자금이 정기예금으로 몰렸다.",
        related_term="정기예금",
        sources=[
            NewsletterIssueSource(
                document_id=47,
                chunk_key="47:0",
                source_url=None,
                evidence_text="금융 근거 본문 0",
            )
        ],
    )


def test_build_issue_generation_prompt_includes_topic_and_evidence() -> None:
    prompt = build_newsletter_issue_generation_prompt(
        topic="정기예금 급증",
        retrieved_chunks=_chunks(),
    )

    assert "정기예금 급증" in prompt
    assert "금융 근거 본문 0" in prompt
    assert "financial_word" in prompt


def test_build_issue_generation_prompt_rejects_blank_topic() -> None:
    with pytest.raises(ValueError, match="주제는 비어 있을 수 없습니다"):
        build_newsletter_issue_generation_prompt(topic="  ", retrieved_chunks=_chunks())


def test_build_issue_generation_prompt_rejects_empty_evidence() -> None:
    with pytest.raises(ValueError, match="검색 근거가 없습니다"):
        build_newsletter_issue_generation_prompt(
            topic="정기예금 급증", retrieved_chunks=[]
        )


def test_build_grounding_validation_prompt_includes_issue_content() -> None:
    prompt = build_newsletter_grounding_validation_prompt(
        issue=_issue_output(),
        retrieved_chunks=_chunks(),
    )

    assert "정기예금 급증" in prompt
    assert "+35조 5,401억 원" in prompt
    assert "금융 근거 본문 0" in prompt


def test_build_headline_prompt_includes_all_issue_titles() -> None:
    issues = [_issue(), _issue(), _issue()]
    prompt = build_newsletter_headline_prompt(issues)

    assert prompt.count("정기예금 급증") >= 3


def test_build_headline_prompt_rejects_empty_issues() -> None:
    with pytest.raises(ValueError, match="이슈가 비어 있습니다"):
        build_newsletter_headline_prompt([])
