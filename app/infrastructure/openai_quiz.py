import functools
import operator
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, create_model

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
    citation_models = tuple(
        _build_citation_model(chunk_key, candidates)
        for chunk_key, candidates in citation_candidates.items()
        if candidates
    )

    if not citation_models:
        raise ValueError("퀴즈 출처 후보는 비어 있을 수 없습니다.")

    # chunk_key와 evidence_text를 청크별로 한 쌍으로 묶어야 한다. 두 필드를
    # 따로 제약하면(예: chunk_key만 Literal로 제한) "존재하는 chunk_key +
    # 남의 청크에서 가져온 evidence_text" 조합을 LLM이 만들 수 있다.
    # 청크마다 별도 모델을 만들고 Union으로 묶어야 그 조합 자체가
    # 스키마에서 불가능해진다.
    citation_type = (
        citation_models[0]
        if len(citation_models) == 1
        else functools.reduce(operator.or_, citation_models)
    )

    return create_model(
        "ConstrainedQuiz",
        __base__=Quiz,
        citations=(list[citation_type], ...),
    )


def _build_citation_model(
    chunk_key: str,
    candidates: Sequence[str],
) -> type[QuizCitation]:
    evidence_text_type = Literal.__getitem__(tuple(candidates))
    safe_name = re.sub(r"\W", "_", chunk_key)

    return create_model(
        f"Citation_{safe_name}",
        __base__=QuizCitation,
        chunk_key=(
            Literal[chunk_key],
            Field(..., json_schema_extra=_use_enum_instead_of_const),
        ),
        evidence_text=(
            evidence_text_type,
            Field(..., json_schema_extra=_use_enum_instead_of_const),
        ),
    )


def _use_enum_instead_of_const(schema: dict[str, Any]) -> None:
    # pydantic은 값이 하나뿐인 Literal을 JSON Schema의 "const"로 내보내는데,
    # OpenAI structured output strict 모드는 "const"를 지원하지 않아 스키마
    # 전체가 거부된다("Invalid schema" 경고, 실제로는 조용히 다른 방식으로
    # 폴백해 검증 없이 호출됨). "enum": [값]은 의미가 같으면서 지원되는
    # 키워드라 여기로 바꿔치기한다.
    if "const" in schema:
        schema["enum"] = [schema.pop("const")]


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
