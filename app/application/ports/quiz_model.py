from dataclasses import dataclass
from typing import Protocol

from app.domain.quiz import GroundingValidation, Quiz


@dataclass(frozen=True, slots=True)
class QuizModelResult:
    quiz: Quiz
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class GroundingModelResult:
    validation: GroundingValidation
    input_tokens: int
    output_tokens: int


class QuizModelClient(Protocol):
    def generate_quiz(
        self,
        prompt: str,
    ) -> QuizModelResult: ...

    def validate_grounding(
        self,
        prompt: str,
    ) -> GroundingModelResult: ...
