from collections.abc import Sequence
from time import monotonic_ns

from app.application.ports.chunk_repository import ChunkRepository
from app.application.ports.quiz_model import QuizModelClient
from app.application.quiz_prompts import (
    build_citation_candidates,
    build_grounding_validation_prompt,
    build_quiz_generation_prompt,
)
from app.application.quiz_sources import build_quiz_sources
from app.application.quiz_validation import (
    align_quiz_citation_evidence,
    validate_quiz_rules,
)
from app.application.search.hybrid import HybridSearch
from app.core.config import Settings
from app.domain.quiz import (
    QuestionType,
    QuizExecution,
    QuizGenerationResult,
    QuizValidation,
)


class QuizGenerationValidationError(ValueError):
    def __init__(
        self,
        errors: Sequence[str],
    ) -> None:
        self.errors = tuple(errors)
        super().__init__("퀴즈 생성 결과 검증에 실패했습니다.")


class QuizGenerationService:
    def __init__(
        self,
        settings: Settings,
        hybrid_search: HybridSearch,
        chunk_repository: ChunkRepository,
        model_client: QuizModelClient,
    ) -> None:
        self._model_name = settings.generation_model
        self._hybrid_search = hybrid_search
        self._chunk_repository = chunk_repository
        self._model_client = model_client

    def generate(
        self,
        *,
        question_type: QuestionType,
        topic: str,
        existing_prompts: Sequence[str] = (),
    ) -> QuizGenerationResult:
        started_at = monotonic_ns()
        search_results = self._hybrid_search.search(topic)
        retrieved_chunks = [result.chunk for result in search_results[:5]]

        if not retrieved_chunks:
            raise QuizGenerationValidationError(["search_result_required"])

        generation_prompt = build_quiz_generation_prompt(
            question_type=question_type,
            topic=topic,
            retrieved_chunks=retrieved_chunks,
        )
        generation_result = self._model_client.generate_quiz(
            generation_prompt,
            build_citation_candidates(retrieved_chunks),
        )
        quiz = align_quiz_citation_evidence(
            quiz=generation_result.quiz,
            retrieved_chunks=retrieved_chunks,
        )
        rule_validation = validate_quiz_rules(
            quiz=quiz,
            retrieved_chunks=retrieved_chunks,
            existing_prompts=existing_prompts,
            expected_question_type=question_type,
        )

        if rule_validation.errors:
            raise QuizGenerationValidationError(rule_validation.errors)

        grounding_prompt = build_grounding_validation_prompt(
            quiz=quiz,
            retrieved_chunks=retrieved_chunks,
        )
        grounding_result = self._model_client.validate_grounding(grounding_prompt)

        if not grounding_result.validation.supported:
            raise QuizGenerationValidationError(["grounding_not_supported"])

        sources = build_quiz_sources(
            quiz=quiz,
            chunk_repository=self._chunk_repository,
        )
        elapsed_ms = max(
            0,
            (monotonic_ns() - started_at) // 1_000_000,
        )

        return QuizGenerationResult(
            quiz=quiz,
            sources=sources,
            validation=QuizValidation(
                schema_valid=True,
                answer_valid=rule_validation.answer_valid,
                citation_valid=rule_validation.citation_valid,
                grounded=True,
                duplicate=rule_validation.duplicate,
                errors=[],
            ),
            execution=QuizExecution(
                model=self._model_name,
                input_tokens=(
                    generation_result.input_tokens + grounding_result.input_tokens
                ),
                output_tokens=(
                    generation_result.output_tokens + grounding_result.output_tokens
                ),
                elapsed_ms=elapsed_ms,
            ),
        )
