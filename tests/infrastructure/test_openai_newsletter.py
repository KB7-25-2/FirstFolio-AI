from unittest.mock import Mock, call

import pytest
from pydantic import ValidationError

from app.domain.newsletter import (
    NewsletterHeadlineOutput,
    NewsletterIssueGenerationOutput,
)
from app.domain.quiz import GroundingValidation
from app.infrastructure import openai_newsletter
from app.infrastructure.openai_newsletter import OpenAINewsletterModelClient


def _issue_output() -> NewsletterIssueGenerationOutput:
    return NewsletterIssueGenerationOutput.model_validate(
        {
            "title": "정기예금 급증",
            "summary": "기업 자금이 정기예금으로 몰렸다.",
            "financial_word": {
                "term": "정기예금",
                "definition": "일정 기간 돈을 맡기는 예금",
            },
            "stat": {"label": "정기예금 증가액", "value": "+35조 5,401억 원"},
            "citations": [
                {"chunk_key": "47:0", "evidence_text": "정기예금 잔액이 크게 늘었다."}
            ],
        }
    )


def _grounding_validation() -> GroundingValidation:
    return GroundingValidation(
        supported=True,
        reason="근거로 뒷받침됩니다.",
        unsupported_claims=[],
    )


def _headline_output() -> NewsletterHeadlineOutput:
    return NewsletterHeadlineOutput(
        headline="역대 최대 흑자 속에서도, 돈은 안전자산으로"
    )


def _citation_candidates() -> dict[str, tuple[str, ...]]:
    return {
        "47:0": ("정기예금 잔액이 크게 늘었다.",),
        "47:1": ("경상수지가 흑자를 기록했다.",),
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
) -> tuple[OpenAINewsletterModelClient, Mock, Mock, Mock, Mock]:
    langchain_client = Mock()
    issue_client = Mock()
    grounding_client = Mock()
    headline_client = Mock()
    langchain_client.with_structured_output.side_effect = [
        grounding_client,
        headline_client,
        issue_client,
    ]
    create_chat_client = Mock(return_value=langchain_client)
    monkeypatch.setattr(openai_newsletter, "ChatOpenAI", create_chat_client)

    client = OpenAINewsletterModelClient(
        model="gpt-4o-mini",
        timeout_seconds=45.0,
        max_retries=3,
    )
    return client, create_chat_client, issue_client, grounding_client, headline_client


def test_configure_gpt_model_and_structured_output_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, create_chat_client, _, _, _ = _create_client(monkeypatch)
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
        call(
            NewsletterHeadlineOutput,
            method="json_schema",
            include_raw=True,
            strict=True,
        ),
    ]


def test_generate_issue_with_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, issue_client, _, _ = _create_client(monkeypatch)
    issue = _issue_output()
    issue_client.invoke.return_value = {
        "raw": _raw_response(input_tokens=135, output_tokens=92),
        "parsed": issue,
        "parsing_error": None,
    }

    result = client.generate_issue("이슈 생성 프롬프트", _citation_candidates())

    assert result.issue == issue
    assert result.input_tokens == 135
    assert result.output_tokens == 92
    issue_client.invoke.assert_called_once_with("이슈 생성 프롬프트")


def test_constrain_citation_to_retrieved_chunk_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, create_chat_client, issue_client, _, _ = _create_client(monkeypatch)
    issue = _issue_output()
    issue_client.invoke.return_value = {
        "raw": _raw_response(),
        "parsed": issue,
        "parsing_error": None,
    }

    client.generate_issue("이슈 생성 프롬프트", _citation_candidates())

    output_model = (
        create_chat_client.return_value.with_structured_output.call_args.args[0]
    )
    output_model.model_validate(issue.model_dump())
    invalid_payload = issue.model_dump()
    invalid_payload["citations"][0]["chunk_key"] = "99:99"

    with pytest.raises(ValidationError):
        output_model.model_validate(invalid_payload)


def test_validate_grounding_with_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _, grounding_client, _ = _create_client(monkeypatch)
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


def test_generate_headline_with_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _, _, headline_client = _create_client(monkeypatch)
    headline = _headline_output()
    headline_client.invoke.return_value = {
        "raw": _raw_response(input_tokens=60, output_tokens=20),
        "parsed": headline,
        "parsing_error": None,
    }

    result = client.generate_headline("헤드라인 프롬프트")

    assert result.headline == headline
    assert result.input_tokens == 60
    assert result.output_tokens == 20


def test_use_zero_when_token_usage_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, issue_client, _, _ = _create_client(monkeypatch)
    raw_response = Mock()
    raw_response.usage_metadata = None
    raw_response.additional_kwargs = {}
    issue_client.invoke.return_value = {
        "raw": raw_response,
        "parsed": _issue_output(),
        "parsing_error": None,
    }

    result = client.generate_issue("이슈 생성 프롬프트", _citation_candidates())

    assert result.input_tokens == 0
    assert result.output_tokens == 0


def test_raise_error_when_structured_output_parsing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, issue_client, _, _ = _create_client(monkeypatch)
    issue_client.invoke.return_value = {
        "raw": _raw_response(),
        "parsed": None,
        "parsing_error": ValueError("invalid JSON"),
    }

    with pytest.raises(ValueError, match="JSON 구조 검증"):
        client.generate_issue("이슈 생성 프롬프트", _citation_candidates())


def test_raise_error_when_model_refuses_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, issue_client, _, _ = _create_client(monkeypatch)
    issue_client.invoke.return_value = {
        "raw": _raw_response(refusal="safety refusal details"),
        "parsed": None,
        "parsing_error": None,
    }

    with pytest.raises(ValueError, match="응답 생성을 거부"):
        client.generate_issue("이슈 생성 프롬프트", _citation_candidates())
