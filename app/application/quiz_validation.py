import random
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.chunk import DocumentChunk
from app.domain.quiz import QuestionType, Quiz, QuizAnswer, QuizOption, UsageType

_NUMERIC_FINANCIAL_CLAIM_PATTERN = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?:조\s*원|억\s*원|만\s*원|천\s*원|원|%|퍼센트|개월|년|일|시간|회)"
)


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


def find_unsupported_numeric_claims(
    quiz: Quiz,
    retrieved_chunks: Sequence[DocumentChunk],
) -> tuple[str, ...]:
    evidence_claims = {
        _normalize_numeric_claim(match.group())
        for chunk in retrieved_chunks[:5]
        for match in _NUMERIC_FINANCIAL_CLAIM_PATTERN.finditer(chunk.content)
    }
    unsupported_claims: list[str] = []

    for target in _numeric_grounding_targets(quiz):
        target_claims = {
            _normalize_numeric_claim(match.group())
            for match in _NUMERIC_FINANCIAL_CLAIM_PATTERN.finditer(target)
        }

        if target_claims - evidence_claims and target not in unsupported_claims:
            unsupported_claims.append(target)

    return tuple(unsupported_claims)


def _numeric_grounding_targets(quiz: Quiz) -> tuple[str, ...]:
    # SCENARIO는 prompt·선택지·해설 수치가 모두 시나리오 설정값이므로 검사하지 않는다.
    # 거짓 수치 방어는 LLM grounding validation(stage 3)이 담당한다.
    if quiz.question_type == QuestionType.SCENARIO:
        return ()

    targets = [quiz.prompt]

    correct_answer_option = next(
        (
            option.text
            for option in quiz.options
            if option.option_id == quiz.correct_answer.option_id
        ),
        None,
    )

    if correct_answer_option is not None:
        targets.append(correct_answer_option)

    targets.append(quiz.explanation)
    return tuple(targets)


def _normalize_numeric_claim(claim: str) -> str:
    normalized = unicodedata.normalize("NFKC", claim)
    return "".join(
        character
        for character in normalized
        if not character.isspace() and character != ","
    )


def shuffle_quiz_options(
    quiz: Quiz,
    rng: random.Random | None = None,
) -> Quiz:
    if quiz.question_type == QuestionType.TRUE_FALSE:
        return quiz

    rng = rng or random.Random()
    target_option_ids = [option.option_id for option in quiz.options]
    shuffled_source_options = list(quiz.options)
    rng.shuffle(shuffled_source_options)

    shuffled_options = [
        QuizOption(option_id=new_id, text=source_option.text)
        for new_id, source_option in zip(
            target_option_ids, shuffled_source_options, strict=True
        )
    ]
    new_correct_option_id = next(
        new_option.option_id
        for new_option, source_option in zip(
            shuffled_options, shuffled_source_options, strict=True
        )
        if source_option.option_id == quiz.correct_answer.option_id
    )

    return quiz.model_copy(
        update={
            "options": shuffled_options,
            "correct_answer": QuizAnswer(option_id=new_correct_option_id),
        }
    )


def align_quiz_citation_evidence(
    quiz: Quiz,
    retrieved_chunks: Sequence[DocumentChunk],
) -> Quiz:
    top_chunks_by_key = {chunk.chunk_key: chunk for chunk in retrieved_chunks[:5]}
    aligned_citations = []

    for citation in quiz.citations:
        chunk = top_chunks_by_key.get(citation.chunk_key)

        if chunk is None:
            aligned_citations.append(citation)
            continue

        aligned_evidence = _find_evidence_ignoring_whitespace(
            content=chunk.content,
            evidence_text=citation.evidence_text,
        )
        aligned_citations.append(
            citation.model_copy(update={"evidence_text": aligned_evidence})
        )

    return quiz.model_copy(update={"citations": aligned_citations})


def _find_evidence_ignoring_whitespace(
    *,
    content: str,
    evidence_text: str,
) -> str:
    if evidence_text in content:
        return evidence_text

    normalized_evidence = "".join(
        character for character in evidence_text if not character.isspace()
    )

    if not normalized_evidence:
        return evidence_text

    normalized_content_characters: list[str] = []
    original_indexes: list[int] = []

    for index, character in enumerate(content):
        if character.isspace():
            continue

        normalized_content_characters.append(character)
        original_indexes.append(index)

    normalized_content = "".join(normalized_content_characters)
    normalized_start = normalized_content.find(normalized_evidence)

    if normalized_start < 0:
        return evidence_text

    normalized_end = normalized_start + len(normalized_evidence) - 1
    original_start = original_indexes[normalized_start]
    original_end = original_indexes[normalized_end] + 1
    return content[original_start:original_end]


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
