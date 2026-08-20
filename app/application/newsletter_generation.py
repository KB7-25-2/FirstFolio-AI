from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.application.newsletter_collection import NewsletterIssueCandidate
from app.application.newsletter_prompts import (
    build_newsletter_grounding_validation_prompt,
    build_newsletter_headline_prompt,
    build_newsletter_issue_generation_prompt,
)
from app.application.newsletter_sources import build_newsletter_issue_sources
from app.application.ports.chunk_repository import ChunkRepository
from app.application.ports.newsletter_model import NewsletterModelClient
from app.application.quiz_prompts import build_citation_candidates
from app.core.config import Settings
from app.domain.newsletter import (
    REQUIRED_SECTION_SIZE,
    FinancialWord,
    NewsletterDraft,
    NewsletterIssue,
    NewsletterStat,
)
from app.domain.quiz import GroundingValidation


class NewsletterIssueGenerationError(ValueError):
    def __init__(
        self,
        errors: Sequence[str],
        *,
        stage: str = "generation_validation",
        grounding_validation: GroundingValidation | None = None,
    ) -> None:
        self.errors = tuple(errors)
        self.stage = stage
        self.reason = (
            grounding_validation.reason if grounding_validation is not None else None
        )
        self.unsupported_claims = (
            tuple(grounding_validation.unsupported_claims)
            if grounding_validation is not None
            else ()
        )
        super().__init__("뉴스레터 이슈 생성 결과 검증에 실패했습니다.")


class NewsletterDraftGenerationError(ValueError):
    def __init__(
        self, failures: Sequence[tuple[NewsletterIssueCandidate, Exception]]
    ) -> None:
        self.failures = tuple(failures)
        super().__init__(
            f"이슈 후보 {len(failures)}건이 모두 실패해 뉴스레터 초안을 만들지 못했습니다."
        )


@dataclass(frozen=True, slots=True)
class NewsletterIssueResult:
    issue: NewsletterIssue
    financial_word: FinancialWord
    stat: NewsletterStat
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class NewsletterDraftResult:
    draft: NewsletterDraft
    skipped_candidates: tuple[NewsletterIssueCandidate, ...]
    input_tokens: int
    output_tokens: int


class NewsletterGenerationService:
    def __init__(
        self,
        settings: Settings,
        chunk_repository: ChunkRepository,
        model_client: NewsletterModelClient,
    ) -> None:
        self._model_name = settings.generation_model
        self._chunk_repository = chunk_repository
        self._model_client = model_client

    def generate_issue(
        self,
        candidate: NewsletterIssueCandidate,
    ) -> NewsletterIssueResult:
        retrieved_chunks = list(candidate.chunks[:5])

        generation_prompt = build_newsletter_issue_generation_prompt(
            topic=candidate.title,
            retrieved_chunks=retrieved_chunks,
        )
        generation_result = self._model_client.generate_issue(
            generation_prompt,
            build_citation_candidates(retrieved_chunks),
        )
        issue_output = generation_result.issue

        grounding_prompt = build_newsletter_grounding_validation_prompt(
            issue=issue_output,
            retrieved_chunks=retrieved_chunks,
        )
        grounding_result = self._model_client.validate_grounding(grounding_prompt)

        if not grounding_result.validation.supported:
            raise NewsletterIssueGenerationError(
                ["grounding_not_supported"],
                stage="grounding_validation",
                grounding_validation=grounding_result.validation,
            )

        sources = build_newsletter_issue_sources(
            issue_output.citations,
            self._chunk_repository,
        )
        if not sources:
            raise NewsletterIssueGenerationError(
                ["source_resolution_failed"],
                stage="source_resolution",
            )

        issue = NewsletterIssue(
            title=issue_output.title,
            summary=issue_output.summary,
            related_term=issue_output.financial_word.term,
            sources=sources,
        )

        return NewsletterIssueResult(
            issue=issue,
            financial_word=issue_output.financial_word,
            stat=issue_output.stat,
            input_tokens=generation_result.input_tokens + grounding_result.input_tokens,
            output_tokens=generation_result.output_tokens
            + grounding_result.output_tokens,
        )

    def generate_headline(
        self,
        issues: Sequence[NewsletterIssue],
    ) -> tuple[str, int, int]:
        prompt = build_newsletter_headline_prompt(issues)
        result = self._model_client.generate_headline(prompt)
        return result.headline.headline, result.input_tokens, result.output_tokens


def generate_newsletter_draft(
    generation_service: NewsletterGenerationService,
    candidates: Sequence[NewsletterIssueCandidate],
    week_start_date: date,
) -> NewsletterDraftResult:
    """이슈 후보를 순서대로 시도해 성공한 이슈 3개를 모을 때까지 생성한다.

    실패한 후보는 건너뛰고 다음 후보로 넘어간다 (전체 배치를 중단하지 않는다).
    호출자는 실패를 감안해 `candidates`에 3개보다 많은 후보를 넘길 수 있다.
    """
    results: list[NewsletterIssueResult] = []
    skipped: list[NewsletterIssueCandidate] = []
    failures: list[tuple[NewsletterIssueCandidate, Exception]] = []

    for candidate in candidates:
        if len(results) >= REQUIRED_SECTION_SIZE:
            break
        try:
            results.append(generation_service.generate_issue(candidate))
        except NewsletterIssueGenerationError as error:
            skipped.append(candidate)
            failures.append((candidate, error))

    if len(results) < REQUIRED_SECTION_SIZE:
        raise NewsletterDraftGenerationError(failures)

    issues = [result.issue for result in results]
    headline, headline_input_tokens, headline_output_tokens = (
        generation_service.generate_headline(issues)
    )

    draft = NewsletterDraft(
        week_start_date=week_start_date,
        headline=headline,
        financial_words_json=[result.financial_word for result in results],
        issues_json=issues,
        stats_json=[result.stat for result in results],
    )

    return NewsletterDraftResult(
        draft=draft,
        skipped_candidates=tuple(skipped),
        input_tokens=sum(result.input_tokens for result in results)
        + headline_input_tokens,
        output_tokens=sum(result.output_tokens for result in results)
        + headline_output_tokens,
    )
