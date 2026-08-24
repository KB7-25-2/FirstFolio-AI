import random
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.chunk import DocumentChunk
from app.domain.quiz import QuestionType, Quiz, QuizAnswer, QuizOption, UsageType

_NUMERIC_FINANCIAL_CLAIM_PATTERN = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?:조\s*원|억\s*원|만\s*원|천\s*원|원|%|퍼센트|개월|년|일|시간|회)"
)
_ENGLISH_WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]*")
_OPTION_TEXT_SEPARATOR_PATTERN = re.compile(r"[\W_]+", re.UNICODE)
_CONTENT_WORD_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
_KOREAN_COUNT_PATTERN = re.compile(
    r"(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*가지"
)
_CONTENT_WORD_STOPWORDS = {
    "가장",
    "것은",
    "대한",
    "대해",
    "따라",
    "통해",
    "한다",
    "있다",
    "없다",
    "이다",
}
_KOREAN_PARTICLE_SUFFIXES = (
    "이다",
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "처럼",
    "보다",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "의",
    "로",
    "과",
    "와",
    "도",
    "만",
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

    targets = []

    # X가 정답인 OX 문항의 prompt는 의도적으로 거짓인 문장이다. 근거에 없는
    # 수치가 들어 있다는 이유만으로 코드 단계에서 차단하지 않고, explanation이
    # 근거의 실제 수치로 올바르게 반박하는지를 grounding 검증에 맡긴다.
    if not (
        quiz.question_type == QuestionType.TRUE_FALSE
        and quiz.correct_answer.option_id == "X"
    ):
        targets.append(quiz.prompt)

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


def _find_unapproved_english_terms(
    quiz: Quiz,
    retrieved_chunks: Sequence[DocumentChunk],
) -> tuple[str, ...]:
    evidence_text = "\n".join(
        chunk.content for chunk in retrieved_chunks[:5]
    ).casefold()
    unapproved_terms: list[str] = []

    for text in _quiz_free_texts(quiz):
        for match in _ENGLISH_WORD_PATTERN.finditer(text):
            term = match.group()

            if len(term) < 2 or term.casefold() in evidence_text:
                continue

            if term not in unapproved_terms:
                unapproved_terms.append(term)

    return tuple(unapproved_terms)


def _quiz_free_texts(quiz: Quiz) -> tuple[str, ...]:
    texts = [
        quiz.prompt,
        quiz.explanation,
        *(option.text for option in quiz.options),
    ]

    if quiz.scenario_json is not None:
        scenario = quiz.scenario_json
        texts.extend(
            [
                scenario.title,
                scenario.persona.name,
                scenario.persona.age,
                scenario.persona.job,
                scenario.requirements.assets,
                scenario.requirements.risk,
                scenario.requirements.goal,
                scenario.narrative,
                scenario.market.title,
                *scenario.market.bullets,
                *scenario.constraints,
                scenario.paper_title,
            ]
        )

    return tuple(texts)


def _normalize_option_text(text: str) -> str:
    return _OPTION_TEXT_SEPARATOR_PATTERN.sub("", text).casefold()


def _find_overlapping_option_text_error(quiz: Quiz) -> str | None:
    if quiz.question_type == QuestionType.TRUE_FALSE:
        return None

    normalized_texts = [_normalize_option_text(option.text) for option in quiz.options]

    if len(normalized_texts) != len(set(normalized_texts)):
        return "duplicate_option_text"

    for index, left in enumerate(normalized_texts):
        if len(left) < 3:
            continue

        for right in normalized_texts[index + 1 :]:
            if len(right) >= 3 and (left in right or right in left):
                return "overlapping_option_text"

    return None


def _normalize_content_words(text: str) -> set[str]:
    words: set[str] = set()

    for match in _CONTENT_WORD_PATTERN.finditer(text):
        word = match.group().casefold()

        for suffix in _KOREAN_PARTICLE_SUFFIXES:
            if word.endswith(suffix) and len(word) > len(suffix) + 1:
                word = word[: -len(suffix)]
                break

        if len(word) >= 2 and word not in _CONTENT_WORD_STOPWORDS:
            words.add(word)

    return words


def _citation_support_target(quiz: Quiz) -> str | None:
    if quiz.question_type == QuestionType.TRUE_FALSE:
        return quiz.explanation if quiz.correct_answer.option_id == "X" else quiz.prompt

    return next(
        (
            option.text
            for option in quiz.options
            if option.option_id == quiz.correct_answer.option_id
        ),
        None,
    )


def _citations_directly_support_answer(quiz: Quiz) -> bool:
    support_target = _citation_support_target(quiz)

    # 정답 선택지를 못 찾는 경우는 구조 검증에서 별도로 잡는다.
    if support_target is None:
        return True

    target_words = _normalize_content_words(support_target)
    citation_words = _normalize_content_words(
        " ".join(citation.evidence_text for citation in quiz.citations)
    )

    return not target_words or bool(target_words & citation_words)


def _find_unsupported_citation_counts(quiz: Quiz) -> tuple[str, ...]:
    citation_counts = {
        "".join(match.group().split())
        for citation in quiz.citations
        for match in _KOREAN_COUNT_PATTERN.finditer(citation.evidence_text)
    }
    unsupported_counts: list[str] = []

    targets = [quiz.explanation]

    if not (
        quiz.question_type == QuestionType.TRUE_FALSE
        and quiz.correct_answer.option_id == "X"
    ):
        targets.append(quiz.prompt)

    if quiz.question_type != QuestionType.TRUE_FALSE:
        support_target = _citation_support_target(quiz)

        if support_target is not None:
            targets.append(support_target)

    for target in targets:
        for match in _KOREAN_COUNT_PATTERN.finditer(target):
            normalized_count = "".join(match.group().split())

            if (
                normalized_count not in citation_counts
                and normalized_count not in unsupported_counts
            ):
                unsupported_counts.append(normalized_count)

    return tuple(unsupported_counts)


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


def stamp_scenario_market_reference_at(quiz: Quiz, now: datetime) -> Quiz:
    """SCENARIO의 market.reference_at을 실제 생성 시각으로 덮어쓴다.

    market.bullets는 정적인 검색 근거에서 뽑은 내용이라 진짜 시장 데이터
    기준 시점이 존재하지 않는다. LLM이 이 값을 임의로 지어내지 않도록,
    모델 출력과 무관하게 항상 실제 생성 시각으로 고정한다.
    """
    if quiz.scenario_json is None:
        return quiz

    updated_market = quiz.scenario_json.market.model_copy(update={"reference_at": now})
    updated_scenario = quiz.scenario_json.model_copy(update={"market": updated_market})
    return quiz.model_copy(update={"scenario_json": updated_scenario})


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
    expected_usage_type: UsageType | None = None,
) -> QuizRuleValidation:
    answer_errors: list[str] = []
    citation_errors: list[str] = []

    if (
        expected_question_type is not None
        and quiz.question_type != expected_question_type
    ):
        answer_errors.append("question_type_mismatch")

    expected_usage = (
        expected_usage_type
        or {
            QuestionType.TRUE_FALSE: UsageType.SUB_CHAPTER,
            QuestionType.SINGLE_CHOICE: UsageType.SUB_CHAPTER,
            QuestionType.SCENARIO: UsageType.MAIN_CHAPTER,
        }[quiz.question_type]
    )
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

    option_text_error = _find_overlapping_option_text_error(quiz)

    if option_text_error is not None:
        answer_errors.append(option_text_error)

    if not quiz.explanation.strip():
        answer_errors.append("explanation_required")

    if quiz.question_type == QuestionType.SCENARIO:
        if quiz.scenario_json is None:
            answer_errors.append("scenario_required")
    elif quiz.scenario_json is not None:
        answer_errors.append("scenario_not_allowed")

    answer_errors.extend(
        f"unapproved_english_term:{term}"
        for term in _find_unapproved_english_terms(quiz, retrieved_chunks)
    )

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

    if not citation_errors and not _citations_directly_support_answer(quiz):
        citation_errors.append("citation_not_supporting_answer")

    if not citation_errors:
        citation_errors.extend(
            f"citation_count_not_supported:{count}"
            for count in _find_unsupported_citation_counts(quiz)
        )

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
