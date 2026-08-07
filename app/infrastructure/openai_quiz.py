from collections.abc import Mapping, Sequence
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, create_model

from app.application.ports.quiz_model import (
    GroundingModelResult,
    QuizModelResult,
)
from app.domain.quiz import GroundingValidation, Quiz, QuizCitation


class OpenAIQuizModelClient:
    def __init__(
        self,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        client = ChatOpenAI(
            model=model,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self._client = client
        self._grounding_client = client.with_structured_output(
            GroundingValidation,
            method="json_schema",
            include_raw=True,
            strict=True,
        )

    def generate_quiz(
        self,
        prompt: str,
        citation_candidates: Mapping[str, Sequence[str]],
    ) -> QuizModelResult:
        output_model = _build_quiz_output_model(citation_candidates)
        quiz_client = self._client.with_structured_output(
            output_model,
            method="json_schema",
            include_raw=True,
            strict=True,
        )
        response = quiz_client.invoke(prompt)
        quiz, input_tokens, output_tokens = _parse_structured_response(
            response=response,
            expected_type=Quiz,
        )

        return QuizModelResult(
            quiz=quiz,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def validate_grounding(
        self,
        prompt: str,
    ) -> GroundingModelResult:
        response = self._grounding_client.invoke(prompt)
        validation, input_tokens, output_tokens = _parse_structured_response(
            response=response,
            expected_type=GroundingValidation,
        )

        return GroundingModelResult(
            validation=validation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _build_quiz_output_model(
    citation_candidates: Mapping[str, Sequence[str]],
) -> type[Quiz]:
    chunk_keys = tuple(citation_candidates)

    if not chunk_keys:
        raise ValueError("퀴즈 출처 후보는 비어 있을 수 없습니다.")

    chunk_key_type = Literal.__getitem__(chunk_keys)
    citation_model = create_model(
        "ConstrainedQuizCitation",
        __base__=QuizCitation,
        chunk_key=(chunk_key_type, ...),
    )
    return create_model(
        "ConstrainedQuiz",
        __base__=Quiz,
        citations=(list[citation_model], ...),
    )


def _parse_structured_response[StructuredModel: BaseModel](
    *,
    response: Any,
    expected_type: type[StructuredModel],
) -> tuple[StructuredModel, int, int]:
    if not isinstance(response, Mapping):
        raise ValueError("OpenAI 모델이 구조화된 응답을 반환하지 않았습니다.")

    raw_response = response.get("raw")
    parsing_error = response.get("parsing_error")
    parsed = response.get("parsed")

    if _is_refusal(raw_response):
        raise ValueError("OpenAI 모델이 응답 생성을 거부했습니다.")

    if parsing_error is not None:
        raise ValueError(
            "OpenAI 모델 응답의 JSON 구조 검증에 실패했습니다."
        ) from parsing_error

    if not isinstance(parsed, expected_type):
        raise ValueError("OpenAI 모델이 구조화된 응답을 반환하지 않았습니다.")

    input_tokens, output_tokens = _extract_token_usage(raw_response)
    return parsed, input_tokens, output_tokens


def _is_refusal(raw_response: Any) -> bool:
    additional_kwargs = getattr(raw_response, "additional_kwargs", None)
    return isinstance(additional_kwargs, Mapping) and bool(
        additional_kwargs.get("refusal")
    )


def _extract_token_usage(raw_response: Any) -> tuple[int, int]:
    usage_metadata = getattr(raw_response, "usage_metadata", None)

    if not isinstance(usage_metadata, Mapping):
        return 0, 0

    input_tokens = usage_metadata.get("input_tokens", 0)
    output_tokens = usage_metadata.get("output_tokens", 0)

    return int(input_tokens), int(output_tokens)
