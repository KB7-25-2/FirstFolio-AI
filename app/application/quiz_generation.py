import random
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
    find_unsupported_numeric_claims,
    shuffle_quiz_options,
    validate_quiz_rules,
)
from app.application.search.hybrid import HybridSearch
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.quiz import (
    GroundingValidation,
    QuestionType,
    Quiz,
    QuizExecution,
    QuizGenerationResult,
    QuizValidation,
)


class QuizGenerationValidationError(ValueError):
    def __init__(
        self,
        errors: Sequence[str],
        *,
        stage: str = "generation_validation",
        retrieved_chunks: Sequence[DocumentChunk] = (),
        quiz: Quiz | None = None,
        grounding_validation: GroundingValidation | None = None,
    ) -> None:
        self.errors = tuple(errors)
        self.stage = stage
        self.retrieved_chunks = tuple(retrieved_chunks)
        self.quiz = quiz
        self.grounding_validation = grounding_validation
        self.reason = (
            grounding_validation.reason if grounding_validation is not None else None
        )
        self.unsupported_claims = (
            tuple(grounding_validation.unsupported_claims)
            if grounding_validation is not None
            else ()
        )
        super().__init__("퀴즈 생성 결과 검증에 실패했습니다.")


class QuizGenerationService:
    def __init__(
        self,
        settings: Settings,
        hybrid_search: HybridSearch,
        chunk_repository: ChunkRepository,
        model_client: QuizModelClient,
        rng: random.Random | None = None,
    ) -> None:
        self._model_name = settings.generation_model
        self._hybrid_search = hybrid_search
        self._chunk_repository = chunk_repository
        self._model_client = model_client
        self._rng = rng or random.Random()

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
            raise QuizGenerationValidationError(
                ["search_result_required"],
                stage="search",
            )

        true_false_target = (
            self._rng.choice(["O", "X"])
            if question_type == QuestionType.TRUE_FALSE
            else None
        )
        generation_prompt = build_quiz_generation_prompt(
            question_type=question_type,
            topic=topic,
            retrieved_chunks=retrieved_chunks,
            true_false_target=true_false_target,
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
            raise QuizGenerationValidationError(
                rule_validation.errors,
                stage="generation_validation",
                retrieved_chunks=retrieved_chunks,
                quiz=quiz,
            )

        unsupported_numeric_claims = find_unsupported_numeric_claims(
            quiz=quiz,
            retrieved_chunks=retrieved_chunks,
        )

        if unsupported_numeric_claims:
            raise QuizGenerationValidationError(
                ["grounding_not_supported"],
                stage="grounding_validation",
                retrieved_chunks=retrieved_chunks,
                quiz=quiz,
                grounding_validation=GroundingValidation(
                    supported=False,
                    reason=(
                        "질문, 시나리오, 정답 선택지 또는 해설에 검색 근거로 "
                        "확인할 수 없는 금융 수치가 있습니다."
                    ),
                    unsupported_claims=list(unsupported_numeric_claims),
                ),
            )

        grounding_prompt = build_grounding_validation_prompt(
            quiz=quiz,
            retrieved_chunks=retrieved_chunks,
        )
        grounding_result = self._model_client.validate_grounding(grounding_prompt)

        if not grounding_result.validation.supported:
            raise QuizGenerationValidationError(
                ["grounding_not_supported"],
                stage="grounding_validation",
                retrieved_chunks=retrieved_chunks,
                quiz=quiz,
                grounding_validation=grounding_result.validation,
            )

        sources = build_quiz_sources(
            quiz=quiz,
            chunk_repository=self._chunk_repository,
        )
        quiz = shuffle_quiz_options(quiz, rng=self._rng)
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
