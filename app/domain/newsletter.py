from datetime import date

from pydantic import BaseModel, ConfigDict, Field

REQUIRED_SECTION_SIZE = 3
"""financial_words_json·issues_json·stats_json은 BE 검증 규칙상 정확히 3개여야 한다."""


class FinancialWord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class NewsletterIssueSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int = Field(ge=1)
    chunk_key: str = Field(min_length=1)
    source_url: str | None = None
    evidence_text: str = Field(min_length=1)


class NewsletterIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    related_term: str = Field(min_length=1)
    sources: list[NewsletterIssueSource] = Field(min_length=1)


class NewsletterStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class NewsletterCitation(BaseModel):
    """LLM이 생성 단계에서 직접 반환하는 인용 — chunk_repository로 보강되기 전.

    보강 후 최종적으로 `NewsletterIssueSource`(document_id·source_url 포함)가 된다.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_key: str = Field(min_length=1)
    evidence_text: str = Field(min_length=1)


class NewsletterIssueGenerationOutput(BaseModel):
    """이슈 하나에 대한 LLM 생성 결과 — 최종 `NewsletterIssue`가 되기 전 원본."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    financial_word: FinancialWord
    stat: NewsletterStat
    citations: list[NewsletterCitation] = Field(min_length=1)


class NewsletterHeadlineOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1)


class NewsletterDraft(BaseModel):
    """AI가 생성해 BE `POST /api/internal/newsletters`로 보내는 페이로드.

    필드명·구조는 BE `NewsletterCreateRequest`와 1:1로 대응한다.
    """

    model_config = ConfigDict(extra="forbid")

    week_start_date: date
    headline: str = Field(min_length=1)
    financial_words_json: list[FinancialWord] = Field(
        min_length=REQUIRED_SECTION_SIZE, max_length=REQUIRED_SECTION_SIZE
    )
    issues_json: list[NewsletterIssue] = Field(
        min_length=REQUIRED_SECTION_SIZE, max_length=REQUIRED_SECTION_SIZE
    )
    stats_json: list[NewsletterStat] = Field(
        min_length=REQUIRED_SECTION_SIZE, max_length=REQUIRED_SECTION_SIZE
    )


class NewsletterDeliveryResponse(BaseModel):
    """BE `POST /api/internal/newsletters` 응답."""

    model_config = ConfigDict(extra="forbid")

    newsletter_id: int
    week_start_date: date
    status: str
