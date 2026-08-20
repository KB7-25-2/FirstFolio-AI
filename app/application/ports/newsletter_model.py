from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.application.ports.quiz_model import GroundingModelResult
from app.domain.newsletter import (
    NewsletterHeadlineOutput,
    NewsletterIssueGenerationOutput,
)


@dataclass(frozen=True, slots=True)
class NewsletterIssueModelResult:
    issue: NewsletterIssueGenerationOutput
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class NewsletterHeadlineModelResult:
    headline: NewsletterHeadlineOutput
    input_tokens: int
    output_tokens: int


class NewsletterModelClient(Protocol):
    def generate_issue(
        self,
        prompt: str,
        citation_candidates: Mapping[str, Sequence[str]],
    ) -> NewsletterIssueModelResult: ...

    def validate_grounding(
        self,
        prompt: str,
    ) -> GroundingModelResult: ...

    def generate_headline(
        self,
        prompt: str,
    ) -> NewsletterHeadlineModelResult: ...
