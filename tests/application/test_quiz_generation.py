import random
from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.application.ports.quiz_model import (
    GroundingModelResult,
    QuizModelClient,
    QuizModelResult,
)
from app.application.quiz_generation import (
    QuizGenerationService,
    QuizGenerationValidationError,
)
from app.application.search.hybrid import HybridSearch
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.quiz import GroundingValidation, QuestionType, Quiz
from app.domain.search import SearchResult
from app.infrastructure.repositories.in_memory_chunk import InMemoryChunkRepository


def _chunks(count: int = 6) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            document_id="47",
            chunk_key=f"47:{index}",
            sequence=index,
            content=(
                "예금은 금융기관에 돈을 맡기는 금융상품이다."
                if index == 0
                else f"금융 교육 근거 {index}"
            ),
            title="금융 교과서",
            source="financial_textbook.txt",
            heading="저축과 저축 상품",
        )
        for index in range(count)
    ]


def _quiz(
    question_type: QuestionType = QuestionType.SINGLE_CHOICE,
    **changes: object,
) -> Quiz:
    if question_type == QuestionType.TRUE_FALSE:
        options = [
            {"option_id": "O", "text": "O"},
            {"option_id": "X", "text": "X"},
        ]
        correct_answer = {"option_id": "O"}
    else:
        options = [
            {"option_id": "1", "text": "선택지 1"},
            {"option_id": "2", "text": "선택지 2"},
            {"option_id": "3", "text": "선택지 3"},
            {"option_id": "4", "text": "선택지 4"},
        ]
        correct_answer = {"option_id": "1"}

    scenario_json = None
    usage_type = "SUB_CHAPTER"

    if question_type == QuestionType.SCENARIO:
        usage_type = "MAIN_CHAPTER"
        scenario_json = {
            "title": "금융상품 선택",
            "narrative": "안정적인 저축을 원하는 학생이 매달 용돈을 받고 있다.",
            "persona": {"name": "민서", "age": "18세", "job": "고등학생"},
            "requirements": {
                "assets": "매달 받는 용돈",
                "risk": "원금 손실을 피하고 싶음",
                "goal": "안정적으로 저축하기",
            },
            "market": {
                "title": "시장 정보",
                "reference_at": "2026-08-10T00:00:00Z",
                "bullets": ["검증된 시장 정보"],
            },
            "constraints": ["원금 손실을 피해야 한다."],
            "paper_title": "선택 보고서",
        }

    payload: dict[str, object] = {
        "usage_type": usage_type,
        "question_type": question_type,
        "prompt": "예금에 대한 설명으로 옳은 것은?",
        "scenario_json": scenario_json,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
        "difficulty": "EASY",
        "citations": [
            {
                "chunk_key": "47:0",
                "evidence_text": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
            }
        ],
    }
    payload.update(changes)
    return Quiz.model_validate(payload)


def _service(
    *,
    quiz: Quiz | None = None,
    chunks: list[DocumentChunk] | None = None,
    search_results: list[SearchResult] | None = None,
    supported: bool = True,
    rng: random.Random | None = None,
) -> tuple[
    QuizGenerationService,
    Mock,
    InMemoryChunkRepository,
]:
    chunks = chunks or _chunks()
    repository = InMemoryChunkRepository()
    repository.save_all(chunks)
    hybrid_search = Mock(spec=HybridSearch)
    hybrid_search.search.return_value = (
        search_results
        if search_results is not None
        else [SearchResult(chunk=chunk, score=1.0) for chunk in chunks]
    )
    model_client = Mock(spec=QuizModelClient)
    model_client.generate_quiz.return_value = QuizModelResult(
        quiz=quiz or _quiz(),
        input_tokens=120,
        output_tokens=80,
    )
    model_client.validate_grounding.return_value = GroundingModelResult(
        validation=GroundingValidation(
            supported=supported,
            reason=(
                "검색 근거로 뒷받침됩니다." if supported else "검색 근거가 부족합니다."
            ),
            unsupported_claims=[] if supported else ["근거 없는 주장"],
        ),
        input_tokens=40,
        output_tokens=20,
    )
    service = QuizGenerationService(
        settings=Settings(
            generation_model="gpt-4o-mini",
            _env_file=None,
        ),
        hybrid_search=hybrid_search,
        chunk_repository=repository,
        model_client=model_client,
        rng=rng,
    )
    return service, model_client, repository


@pytest.fixture
def actual_grounding_failure_case() -> tuple[
    list[DocumentChunk],
    Quiz,
    GroundingValidation,
]:
    chunks = [
        DocumentChunk(
            document_id="47",
            chunk_key="47:189",
            sequence=189,
            content=(
                "저축 상품의 종류와 특징 가계가 여유 자금을 은행에 맡기고 "
                "취득하는 저축 상품은 크게 요구불 예금과 저 축성 예금으로 나눌 수 "
                "있다. 요구불 예금이란 수시로 하는 입출금이 자유롭다. 그 런데 은행의 "
                "입장에서는 예금자가계좌에서 언제 얼마를 인출할지 알 수 없는 예금 "
                "이다. 은행은 요구불 예금 계좌에 들어있는 예금은 안심하고 대출에 "
                "사용해서 수억을 내기 어려우므로 예금자에게 낮은 금리를 지급한나. 시중 "
                "은행이 공지하는 평균 적인 요구불 예금 금리는 0.1% 정도 수준으로 낮다. "
                "가계는 지출에 쓸 돈을 수중에 지니기보다는 요구불 예금 계좌에 넣어 놓고, "
                "신용카드나 직불 카드를 그 계죄와 연결하여 사용함으로써 지출이 편리해진다. "
                "요구불 혜금은 지급의 편의성을 위한 예금이지 이자 수익을 올리기 위한 예금이 "
                "아니다. 직 장에서는 직원이 지정한 요구불 예금 계좌에 그의 급여를 입금해 "
                "준다, 요구불 예금에 들어 있는 돈은 이름만 예금일 뿐이지 현금이나 "
                "마찬가지다. -계 1현.신 (연 다, %그일 1-@/ 급너가 시눌메 쓰미시싸시피 과잉"
            ),
            title="금융 교과서",
            source="financial_textbook.txt",
        ),
        DocumentChunk(
            document_id="47",
            chunk_key="47:188",
            sequence=188,
            content=(
                "가계는 저축으로 생긴 여유 자금을 은행, 상호 저축 은행, 신용 험동조함 "
                "동의 예 금 기관에서 제공하는 저축 상품에 넣을 수 있다. 예금이나 적금이 "
                "대표적인 저축 상 품이다. 저축 상품은 돈을 맡긴 은행이 망 하지 않는 한 "
                "원금이 보장된다. 따라서 저 축 상품은 안전하게 위험 없이 돈을 모으는 데 "
                "적합한 금융 수단이다. 이에 비해서 투자 상품이란 투자한 금융 자산의 가격이 "
                "변 동하여 원금 손실의 위험이 있는 금융 상품 이다. 주식, 채권, 펀드, 피생 "
                "금융 상품 등이 대표적이다. 저축 상품과 투자 상품의 좋류와 특징에 대해서 "
                "알아보자."
            ),
            title="금융 교과서",
            source="financial_textbook.txt",
        ),
        DocumentChunk(
            document_id="47",
            chunk_key="47:274",
            sequence=274,
            content=(
                "주식이나 채권, 부동산 등 자산 시장의 중요한 특징 가운데 하나는 미래의 "
                "자산 가 격에 대한 사람들의 전망이 지금 그 자산의 가격에 바로 영향을 미친다는 "
                "점이다. 앞"
            ),
            title="금융 교과서",
            source="financial_textbook.txt",
        ),
        DocumentChunk(
            document_id="47",
            chunk_key="47:217",
            sequence=217,
            content=(
                "2) 채권, 주식, 펀드\n투자 성격을 지닌 금융 상품에는 채권, 주식, 펀드, "
                "파생 금융 상품이 있다. 그중에 서 주식이나 채권처럼 매매가 가능한 금융 투자 "
                "상품을 증권이라고 한다. 채권, 주 식, 펀드 등이 지닌 각각의 성격과 특징을 "
                "자세히 알아보자. 채권"
            ),
            title="금융 교과서",
            source="financial_textbook.txt",
        ),
        DocumentChunk(
            document_id="47",
            chunk_key="47:190",
            sequence=190,
            content=(
                "저축성 예금에는 정기 예금과 정기 적금이 있다. 정기 예금은 일정한 액수의 돈을 "
                "은행에 맡겨 두고 정하는 기간 동안 인춤하지 않겠다고 은행과 약속하는 형식의 "
                "예 금이다. 정기 예금의 가능한 약정 기간은 1개월 이상 5년 이내이다. 은행으로서는 "
                "정 기 예금 계좌에 들어 있는 돈은 약정 기간 동안 안심하고 대출에 이용해서 "
                "수익을 올 릴 수 있기 떠문에 요구불 예금보다 더 높은 금리를 지급한다. 일반적으로 "
                "예치 약정 기간이 길수록 정기 예금 금리는 높아진다."
            ),
            title="금융 교과서",
            source="financial_textbook.txt",
        ),
    ]
    quiz = _quiz(
        prompt="저축 상품의 종류 중 요구불 예금의 특징으로 옭은 것은 무엇인가요?",
        options=[
            {"option_id": "1", "text": "요구불 예금은 수시로 입출금이 가능하다."},
            {"option_id": "2", "text": "요구불 예금은 원금이 보장되지 않는다."},
            {"option_id": "3", "text": "요구불 예금의 금리는 보통 높다."},
            {"option_id": "4", "text": "요구불 예금은 장기 투자에 적합하다."},
        ],
        explanation="요구불 예금이란 수시로 하는 입출금이 자유롭다.",
        citations=[
            {
                "chunk_key": "47:189",
                "evidence_text": "요구불 예금이란 수시로 하는 입출금이 자유롭다.",
            }
        ],
    )
    validation = GroundingValidation(
        supported=False,
        reason=(
            "The claim that '요구불 예금은 원금이 보장되지 않는다' (option 2) "
            "is unsupported by the provided evidence. It is stated that '저축 상품은 "
            "돈을 맡긴 은행이 망하지 않는 한 원금이 보장된다', which implies that "
            "요구불 예금 does provide principal protection."
        ),
        unsupported_claims=[
            "요구불 예금은 원금이 보장되지 않는다.",
            "요구불 예금의 금리는 보통 높다.",
            "요구불 예금은 장기 투자에 적합하다.",
        ],
    )
    return chunks, quiz, validation


@pytest.mark.parametrize(
    "question_type",
    [
        QuestionType.TRUE_FALSE,
        QuestionType.SINGLE_CHOICE,
        QuestionType.SCENARIO,
    ],
)
def test_generate_valid_quiz_result(
    question_type: QuestionType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, model_client, _ = _service(quiz=_quiz(question_type))
    clock = Mock(side_effect=[1_000_000, 16_000_000])
    monkeypatch.setattr(
        "app.application.quiz_generation.monotonic_ns",
        clock,
    )

    result = service.generate(
        question_type=question_type,
        topic="예금",
    )

    assert result.quiz.question_type == question_type
    assert result.sources[0].chunk_key == "47:0"
    assert result.sources[0].title == "금융 교과서"
    assert result.validation.model_dump() == {
        "schema_valid": True,
        "answer_valid": True,
        "citation_valid": True,
        "grounded": True,
        "duplicate": False,
        "errors": [],
    }
    assert result.execution.model == "gpt-4o-mini"
    assert result.execution.input_tokens == 160
    assert result.execution.output_tokens == 100
    assert result.execution.elapsed_ms == 15
    generation_prompt = model_client.generate_quiz.call_args.args[0]
    assert 'chunk_key="47:4"' in generation_prompt
    assert 'chunk_key="47:5"' not in generation_prompt


@pytest.mark.parametrize(
    ("seed", "expected_target"),
    [(0, "X"), (1, "O")],
)
def test_generate_true_false_quiz_requests_random_target_answer(
    seed: int,
    expected_target: str,
) -> None:
    service, model_client, _ = _service(
        quiz=_quiz(QuestionType.TRUE_FALSE),
        rng=random.Random(seed),
    )

    service.generate(
        question_type=QuestionType.TRUE_FALSE,
        topic="예금",
    )

    generation_prompt = model_client.generate_quiz.call_args.args[0]
    assert f'correct_answer.option_id는 반드시 "{expected_target}"' in generation_prompt


def test_stop_before_generation_without_search_result() -> None:
    service, model_client, _ = _service(search_results=[])

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
        )

    assert error.value.errors == ("search_result_required",)
    assert error.value.stage == "search"
    assert error.value.retrieved_chunks == ()
    assert error.value.quiz is None
    assert error.value.reason is None
    assert error.value.unsupported_claims == ()
    model_client.generate_quiz.assert_not_called()
    model_client.validate_grounding.assert_not_called()


def test_reject_generated_question_type_different_from_request() -> None:
    service, model_client, _ = _service(quiz=_quiz(QuestionType.SCENARIO))

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
        )

    assert "question_type_mismatch" in error.value.errors
    assert error.value.stage == "generation_validation"
    assert len(error.value.retrieved_chunks) == 5
    assert error.value.quiz is not None
    assert error.value.grounding_validation is None
    model_client.validate_grounding.assert_not_called()


def test_restore_whitespace_only_citation_before_validation() -> None:
    chunks = _chunks()
    chunks[0] = replace(
        chunks[0],
        content="정기 예금은 인출하지 않는 예 금이다.",
    )
    quiz = _quiz(
        citations=[
            {
                "chunk_key": "47:0",
                "evidence_text": "정기 예금은 인출하지 않는 예금이다.",
            }
        ]
    )
    service, model_client, _ = _service(quiz=quiz, chunks=chunks)

    result = service.generate(
        question_type=QuestionType.SINGLE_CHOICE,
        topic="예금",
    )

    original_evidence = "정기 예금은 인출하지 않는 예 금이다."
    assert result.quiz.citations[0].evidence_text == original_evidence
    assert result.sources[0].evidence_text == original_evidence
    grounding_prompt = model_client.validate_grounding.call_args.args[0]
    assert original_evidence in grounding_prompt


@pytest.mark.parametrize(
    ("quiz", "existing_prompts", "expected_error"),
    [
        (
            _quiz(correct_answer={"option_id": "5"}),
            [],
            "correct_answer_not_found",
        ),
        (
            _quiz(
                citations=[
                    {
                        "chunk_key": "47:5",
                        "evidence_text": "금융 교육 근거 5",
                    }
                ]
            ),
            [],
            "citation_chunk_not_found:47:5",
        ),
        (
            _quiz(),
            ["예금에 대한 설명으로 옳은 것은!"],
            "duplicate_prompt",
        ),
    ],
)
def test_reject_code_validation_failure_before_grounding(
    quiz: Quiz,
    existing_prompts: list[str],
    expected_error: str,
) -> None:
    service, model_client, _ = _service(quiz=quiz)

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
            existing_prompts=existing_prompts,
        )

    assert expected_error in error.value.errors
    assert error.value.stage == "generation_validation"
    assert len(error.value.retrieved_chunks) == 5
    assert error.value.quiz == quiz
    assert error.value.reason is None
    assert error.value.unsupported_claims == ()
    model_client.validate_grounding.assert_not_called()


def test_reject_unsupported_grounding_result() -> None:
    service, model_client, _ = _service(supported=False)

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
        )

    assert error.value.errors == ("grounding_not_supported",)
    assert error.value.stage == "grounding_validation"
    assert len(error.value.retrieved_chunks) == 5
    assert error.value.quiz == _quiz()
    assert error.value.reason == "검색 근거가 부족합니다."
    assert error.value.unsupported_claims == ("근거 없는 주장",)
    assert error.value.grounding_validation == GroundingValidation(
        supported=False,
        reason="검색 근거가 부족합니다.",
        unsupported_claims=["근거 없는 주장"],
    )
    model_client.validate_grounding.assert_called_once()


def test_reject_numeric_content_expansion_before_llm_grounding() -> None:
    expanded_claim = "요구불 예금은 항상 연 10% 이자를 지급한다."
    quiz = _quiz(explanation=expanded_claim)
    service, model_client, _ = _service(quiz=quiz)
    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
        )

    retrieved_text = " ".join(chunk.content for chunk in error.value.retrieved_chunks)
    assert expanded_claim not in retrieved_text
    assert error.value.stage == "grounding_validation"
    assert error.value.reason == (
        "질문, 시나리오, 정답 선택지 또는 해설에 검색 근거로 확인할 수 없는 "
        "금융 수치가 있습니다."
    )
    assert error.value.unsupported_claims == (expanded_claim,)
    model_client.validate_grounding.assert_not_called()


def test_preserve_actual_overstrict_grounding_failure_fixture(
    actual_grounding_failure_case: tuple[
        list[DocumentChunk],
        Quiz,
        GroundingValidation,
    ],
) -> None:
    chunks, quiz, grounding_validation = actual_grounding_failure_case
    service, model_client, _ = _service(quiz=quiz, chunks=chunks)
    model_client.validate_grounding.return_value = GroundingModelResult(
        validation=grounding_validation,
        input_tokens=0,
        output_tokens=0,
    )

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금의 특징",
        )

    cited_chunk = chunks[0]
    assert quiz.explanation in cited_chunk.content
    assert quiz.citations[0].evidence_text in cited_chunk.content
    assert quiz.correct_answer.option_id == "1"
    assert grounding_validation.unsupported_claims == [
        option.text for option in quiz.options[1:]
    ]
    assert error.value.errors == ("grounding_not_supported",)
    assert error.value.stage == "grounding_validation"
    assert error.value.retrieved_chunks == tuple(chunks)
    assert error.value.quiz == quiz
    assert error.value.grounding_validation == grounding_validation
    assert error.value.reason == grounding_validation.reason
    assert error.value.unsupported_claims == tuple(
        grounding_validation.unsupported_claims
    )


def test_accept_actual_fixture_when_only_incorrect_distractors_lack_support(
    actual_grounding_failure_case: tuple[
        list[DocumentChunk],
        Quiz,
        GroundingValidation,
    ],
) -> None:
    chunks, quiz, _ = actual_grounding_failure_case
    service, model_client, _ = _service(quiz=quiz, chunks=chunks)
    model_client.validate_grounding.return_value = GroundingModelResult(
        validation=GroundingValidation(
            supported=True,
            reason=(
                "질문, 정답 선택지와 해설은 근거로 뒷받침되고 나머지 선택지는 오답이다."
            ),
            unsupported_claims=[],
        ),
        input_tokens=0,
        output_tokens=0,
    )

    result = service.generate(
        question_type=QuestionType.SINGLE_CHOICE,
        topic="예금의 특징",
    )

    assert result.validation.grounded is True
    assert result.quiz.model_dump(exclude={"options", "correct_answer"}) == (
        quiz.model_dump(exclude={"options", "correct_answer"})
    )
    assert {option.text for option in result.quiz.options} == {
        option.text for option in quiz.options
    }
    result_correct_option = next(
        option
        for option in result.quiz.options
        if option.option_id == result.quiz.correct_answer.option_id
    )
    original_correct_option = next(
        option
        for option in quiz.options
        if option.option_id == quiz.correct_answer.option_id
    )
    assert result_correct_option.text == original_correct_option.text
    grounding_prompt = model_client.validate_grounding.call_args.args[0]
    assert "오답 선택지가 검색 근거에서 지원되지 않는다는" in grounding_prompt


def test_reject_when_another_option_can_also_be_correct() -> None:
    quiz = _quiz(
        options=[
            {"option_id": "1", "text": "예금은 금융기관에 돈을 맡기는 상품이다."},
            {"option_id": "2", "text": "예금은 은행에 돈을 맡기는 금융상품이다."},
            {"option_id": "3", "text": "예금은 주식 종목이다."},
            {"option_id": "4", "text": "예금은 실물 자산이다."},
        ]
    )
    service, model_client, _ = _service(quiz=quiz)
    grounding_validation = GroundingValidation(
        supported=False,
        reason="선택지 1과 2가 모두 근거상 정답이 될 수 있다.",
        unsupported_claims=[],
    )
    model_client.validate_grounding.return_value = GroundingModelResult(
        validation=grounding_validation,
        input_tokens=0,
        output_tokens=0,
    )

    with pytest.raises(QuizGenerationValidationError) as error:
        service.generate(
            question_type=QuestionType.SINGLE_CHOICE,
            topic="예금",
        )

    assert error.value.errors == ("grounding_not_supported",)
    assert error.value.reason == grounding_validation.reason
    assert error.value.unsupported_claims == ()


def test_scenario_skips_numeric_check_and_proceeds_to_llm_grounding() -> None:
    chunks = _chunks()
    chunks[0] = replace(
        chunks[0],
        content=(
            "정기 예금의 약정 기간은 1개월 이상 5년 이내이다. "
            "일반적으로 예치 기간이 길수록 금리가 높아진다."
        ),
    )
    quiz = _quiz(
        QuestionType.SCENARIO,
        prompt="어떤 정기 예금 상품을 선택해야 할까요?",
        scenario_json={
            "title": "정기 예금 선택",
            "narrative": "고등학생이 대학 진학을 위해 100만 원을 저축하려고 한다.",
            "persona": {"name": "민서", "age": "18세", "job": "고등학생"},
            "requirements": {
                "assets": "저축 자금 100만 원",
                "risk": "원금 손실을 피하고 싶음",
                "goal": "대학 진학 자금 마련",
            },
            "market": {
                "title": "시장 정보",
                "reference_at": "2026-08-10T00:00:00Z",
                "bullets": ["검증된 시장 정보"],
            },
            "constraints": ["예치 기간이 1개월 이상 5년 이내"],
            "paper_title": "선택 보고서",
        },
        options=[
            {"option_id": "1", "text": "1개월 후 만기, 이자율 1.5%"},
            {"option_id": "2", "text": "1년 후 만기, 이자율 2.0%"},
            {"option_id": "3", "text": "3년 후 만기, 이자율 3.5%"},
            {"option_id": "4", "text": "5년 후 만기, 이자율 4.0%"},
        ],
        correct_answer={"option_id": "4"},
        explanation="100만 원을 5년 동안 4.0% 금리로 맡기는 것이 가장 유리하다.",
        citations=[
            {
                "chunk_key": "47:0",
                "evidence_text": ("정기 예금의 약정 기간은 1개월 이상 5년 이내이다."),
            }
        ],
    )
    service, model_client, _ = _service(quiz=quiz, chunks=chunks)

    result = service.generate(
        question_type=QuestionType.SCENARIO,
        topic="정기 예금 선택 상황",
    )

    assert result.validation.grounded is True
    model_client.validate_grounding.assert_called_once()
