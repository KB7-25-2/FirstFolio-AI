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
