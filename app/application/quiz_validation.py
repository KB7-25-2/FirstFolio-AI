import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.chunk import DocumentChunk
from app.domain.quiz import QuestionType, Quiz, UsageType


@dataclass(frozen=True, slots=True)
class QuizRuleValidation:
    answer_valid: bool
    citation_valid: bool
    duplicate: bool
    errors: tuple[str, ...]


def normalize_quiz_prompt(prompt: str) -> str:
    without_punctuation = "".join(
        character
        for character in prompt
        if not unicodedata.category(character).startswith("P")
    )
    return " ".join(without_punctuation.split())


def validate_quiz_rules(
    quiz: Quiz,
    retrieved_chunks: Sequence[DocumentChunk],
    existing_prompts: Sequence[str] = (),
    expected_question_type: QuestionType | None = None,
) -> QuizRuleValidation:
    answer_errors: list[str] = []
    citation_errors: list[str] = []

    if (
        expected_question_type is not None
        and quiz.question_type != expected_question_type
    ):
        answer_errors.append("question_type_mismatch")

    expected_usage = {
        QuestionType.TRUE_FALSE: UsageType.SUB_CHAPTER,
        QuestionType.SINGLE_CHOICE: UsageType.SUB_CHAPTER,
        QuestionType.SCENARIO: UsageType.MAIN_CHAPTER,
    }[quiz.question_type]
    expected_option_ids = {
        QuestionType.TRUE_FALSE: ["O", "X"],
        QuestionType.SINGLE_CHOICE: ["1", "2", "3", "4"],
        QuestionType.SCENARIO: ["1", "2", "3", "4"],
    }[quiz.question_type]
    option_ids = [option.option_id for option in quiz.options]

    if quiz.usage_type != expected_usage:
        answer_errors.append("usage_type_mismatch")

    if len(quiz.options) != len(expected_option_ids):
        answer_errors.append("invalid_option_count")

    if len(option_ids) != len(set(option_ids)):
        answer_errors.append("duplicate_option_id")

    if option_ids != expected_option_ids:
        answer_errors.append("invalid_option_ids")

    if quiz.question_type == QuestionType.TRUE_FALSE and option_ids == ["O", "X"]:
        option_texts = [option.text for option in quiz.options]

        if option_texts != ["O", "X"]:
            answer_errors.append("invalid_true_false_option_text")

    if quiz.correct_answer.option_id not in option_ids:
        answer_errors.append("correct_answer_not_found")

    if not quiz.explanation.strip():
        answer_errors.append("explanation_required")

    if quiz.question_type == QuestionType.SCENARIO:
        if quiz.scenario_json is None:
            answer_errors.append("scenario_required")
    elif quiz.scenario_json is not None:
        answer_errors.append("scenario_not_allowed")

    top_chunks_by_key = {chunk.chunk_key: chunk for chunk in retrieved_chunks[:5]}

    if not quiz.citations:
        citation_errors.append("citation_required")

    for citation in quiz.citations:
        chunk = top_chunks_by_key.get(citation.chunk_key)

        if chunk is None:
            citation_errors.append(f"citation_chunk_not_found:{citation.chunk_key}")
            continue

        if citation.evidence_text not in chunk.content:
            citation_errors.append(f"citation_evidence_not_found:{citation.chunk_key}")

    normalized_prompt = normalize_quiz_prompt(quiz.prompt)
    normalized_existing_prompts = {
        normalize_quiz_prompt(prompt) for prompt in existing_prompts
    }
    duplicate = normalized_prompt in normalized_existing_prompts
    duplicate_errors = ("duplicate_prompt",) if duplicate else ()

    return QuizRuleValidation(
        answer_valid=not answer_errors,
        citation_valid=not citation_errors,
        duplicate=duplicate,
        errors=tuple(answer_errors) + tuple(citation_errors) + duplicate_errors,
    )
