from unittest.mock import Mock, call

import pytest
from pydantic import ValidationError

from app.domain.quiz import GroundingValidation, Quiz
from app.infrastructure import openai_quiz
from app.infrastructure.openai_quiz import OpenAIQuizModelClient


def _quiz() -> Quiz:
    return Quiz.model_validate(
        {
            "usage_type": "SUB_CHAPTER",
            "question_type": "SINGLE_CHOICE",
            "prompt": "예금에 대한 설명으로 옳은 것은?",
            "scenario_json": None,
            "options": [
                {"option_id": "1", "text": "선택지 1"},
                {"option_id": "2", "text": "선택지 2"},
                {"option_id": "3", "text": "선택지 3"},
                {"option_id": "4", "text": "선택지 4"},
            ],
            "correct_answer": {"option_id": "1"},
            "explanation": "예금은 금융기관에 돈을 맡기는 상품이다.",
            "difficulty": "EASY",
            "citations": [
                {
                    "chunk_key": "47:0",
                    "evidence_text": "예금은 금융기관에 돈을 맡기는 상품이다.",
                }
            ],
        }
    )


def _grounding_validation() -> GroundingValidation:
    return GroundingValidation(
        supported=True,
        reason="문제와 정답이 검색 근거로 뒷받침됩니다.",
        unsupported_claims=[],
    )


def _citation_candidates() -> dict[str, tuple[str, ...]]:
    return {
        "47:0": ("예금은 금융기관에 돈을 맡기는 상품이다.",),
        "47:1": ("적금은 일정한 금액을 정기적으로 납입한다.",),
    }


def _raw_response(
    *,
    input_tokens: int = 120,
    output_tokens: int = 80,
    refusal: str | None = None,
) -> Mock:
    raw_response = Mock()
    raw_response.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    raw_response.additional_kwargs = {}

    if refusal is not None:
        raw_response.additional_kwargs["refusal"] = refusal

    return raw_response


def _create_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[OpenAIQuizModelClient, Mock, Mock, Mock]:
    langchain_client = Mock()
    quiz_client = Mock()
    grounding_client = Mock()
    langchain_client.with_structured_output.side_effect = [
        grounding_client,
        quiz_client,
    ]
    create_chat_client = Mock(return_value=langchain_client)
    monkeypatch.setattr(openai_quiz, "ChatOpenAI", create_chat_client)

    client = OpenAIQuizModelClient(
        model="gpt-4o-mini",
        timeout_seconds=45.0,
        max_retries=3,
    )
    return client, create_chat_client, quiz_client, grounding_client


def test_configure_gpt_model_and_structured_output_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, create_chat_client, _, _ = _create_client(monkeypatch)
    langchain_client = create_chat_client.return_value

    create_chat_client.assert_called_once_with(
        model="gpt-4o-mini",
        timeout=45.0,
        max_retries=3,
    )
    assert langchain_client.with_structured_output.call_args_list == [
        call(
            GroundingValidation,
            method="json_schema",
            include_raw=True,
            strict=True,
        ),
    ]


def test_generate_quiz_with_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, quiz_client, _ = _create_client(monkeypatch)
    quiz = _quiz()
    quiz_client.invoke.return_value = {
        "raw": _raw_response(input_tokens=135, output_tokens=92),
        "parsed": quiz,
        "parsing_error": None,
    }

    result = client.generate_quiz(
        "퀴즈 생성 프롬프트",
        _citation_candidates(),
    )

    assert result.quiz == quiz
    assert result.input_tokens == 135
    assert result.output_tokens == 92
    quiz_client.invoke.assert_called_once_with("퀴즈 생성 프롬프트")


def test_constrain_citation_to_retrieved_chunk_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, create_chat_client, quiz_client, _ = _create_client(monkeypatch)
    quiz = _quiz()
    quiz_client.invoke.return_value = {
        "raw": _raw_response(),
        "parsed": quiz,
        "parsing_error": None,
    }

    client.generate_quiz(
        "퀴즈 생성 프롬프트",
        _citation_candidates(),
    )

    output_model = (
        create_chat_client.return_value.with_structured_output.call_args.args[0]
    )
    output_model.model_validate(quiz.model_dump())
    invalid_payload = quiz.model_dump()
    invalid_payload["citations"][0]["chunk_key"] = "99:99"

    with pytest.raises(ValidationError):
        output_model.model_validate(invalid_payload)


def test_reject_evidence_text_borrowed_from_a_different_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """실제로 관측된 실패 패턴: chunk_key는 실제 존재하는 값이지만
    evidence_text가 다른 청크의 후보 문장인 경우. chunk_key만 제약하던
    이전 구현에서는 이 조합이 그대로 통과했다."""
    client, create_chat_client, quiz_client, _ = _create_client(monkeypatch)
    quiz = _quiz()
    quiz_client.invoke.return_value = {
        "raw": _raw_response(),
        "parsed": quiz,
        "parsing_error": None,
    }

    client.generate_quiz(
        "퀴즈 생성 프롬프트",
        _citation_candidates(),
    )

    output_model = (
        create_chat_client.return_value.with_structured_output.call_args.args[0]
    )
    mismatched_payload = quiz.model_dump()
    mismatched_payload["citations"][0]["chunk_key"] = "47:0"
    mismatched_payload["citations"][0]["evidence_text"] = (
        "적금은 일정한 금액을 정기적으로 납입한다."
    )

    with pytest.raises(ValidationError):
        output_model.model_validate(mismatched_payload)


def test_accept_citation_matching_a_different_valid_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, create_chat_client, quiz_client, _ = _create_client(monkeypatch)
    quiz = _quiz()
    quiz_client.invoke.return_value = {
        "raw": _raw_response(),
        "parsed": quiz,
        "parsing_error": None,
    }

    client.generate_quiz(
        "퀴즈 생성 프롬프트",
        _citation_candidates(),
    )

    output_model = (
        create_chat_client.return_value.with_structured_output.call_args.args[0]
    )
    valid_payload = quiz.model_dump()
    valid_payload["citations"][0]["chunk_key"] = "47:1"
    valid_payload["citations"][0]["evidence_text"] = (
        "적금은 일정한 금액을 정기적으로 납입한다."
    )

    output_model.model_validate(valid_payload)


def test_reject_evidence_text_not_in_any_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, create_chat_client, quiz_client, _ = _create_client(monkeypatch)
    quiz = _quiz()
    quiz_client.invoke.return_value = {
        "raw": _raw_response(),
        "parsed": quiz,
        "parsing_error": None,
    }

    client.generate_quiz(
        "퀴즈 생성 프롬프트",
        _citation_candidates(),
    )

    output_model = (
        create_chat_client.return_value.with_structured_output.call_args.args[0]
    )
    fabricated_payload = quiz.model_dump()
    fabricated_payload["citations"][0]["evidence_text"] = "근거에 없는 새 문장이다."

    with pytest.raises(ValidationError):
        output_model.model_validate(fabricated_payload)


def test_build_output_model_with_single_citation_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, create_chat_client, quiz_client, _ = _create_client(monkeypatch)
    quiz = _quiz()
    quiz_client.invoke.return_value = {
        "raw": _raw_response(),
        "parsed": quiz,
        "parsing_error": None,
    }

    client.generate_quiz(
        "퀴즈 생성 프롬프트",
        {"47:0": ("예금은 금융기관에 돈을 맡기는 상품이다.",)},
    )

    output_model = (
        create_chat_client.return_value.with_structured_output.call_args.args[0]
    )
    output_model.model_validate(quiz.model_dump())


def test_validate_grounding_with_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _, grounding_client = _create_client(monkeypatch)
    validation = _grounding_validation()
    grounding_client.invoke.return_value = {
        "raw": _raw_response(input_tokens=210, output_tokens=35),
        "parsed": validation,
        "parsing_error": None,
    }

    result = client.validate_grounding("근거 검증 프롬프트")

    assert result.validation == validation
    assert result.input_tokens == 210
    assert result.output_tokens == 35
    grounding_client.invoke.assert_called_once_with("근거 검증 프롬프트")


def test_use_zero_when_token_usage_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, quiz_client, _ = _create_client(monkeypatch)
    raw_response = Mock()
    raw_response.usage_metadata = None
    raw_response.additional_kwargs = {}
    quiz_client.invoke.return_value = {
        "raw": raw_response,
        "parsed": _quiz(),
        "parsing_error": None,
    }

    result = client.generate_quiz(
        "퀴즈 생성 프롬프트",
        _citation_candidates(),
    )

    assert result.input_tokens == 0
    assert result.output_tokens == 0


def test_raise_error_when_structured_output_parsing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, quiz_client, _ = _create_client(monkeypatch)
    quiz_client.invoke.return_value = {
        "raw": _raw_response(),
        "parsed": None,
        "parsing_error": ValueError("invalid JSON"),
    }

    with pytest.raises(ValueError, match="JSON 구조 검증"):
        client.generate_quiz(
            "퀴즈 생성 프롬프트",
            _citation_candidates(),
        )


def test_raise_error_when_model_refuses_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, quiz_client, _ = _create_client(monkeypatch)
    quiz_client.invoke.return_value = {
        "raw": _raw_response(refusal="safety refusal details"),
        "parsed": None,
        "parsing_error": None,
    }

    with pytest.raises(ValueError, match="응답 생성을 거부"):
        client.generate_quiz(
            "퀴즈 생성 프롬프트",
            _citation_candidates(),
        )
