import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import httpx
from pydantic import ValidationError

from app.application.quiz_batch import (
    QuizBatchService,
    build_batch_items_from_targets,
    build_main_chapter_items_from_targets,
)
from app.application.quiz_delivery import send_records_to_be
from app.core.config import Settings
from app.domain.quiz import BeBatchResponse, QuestionType
from app.infrastructure.spring_quiz_api_client import SpringQuizApiClient
from app.quiz_batch_dry_run import write_jsonl
from app.quiz_mvp import create_quiz_generation_service

_GENERATION_OUTPUT_DIRECTORY = Path("data/local/quiz-generation-batches")
_DELIVERY_OUTPUT_DIRECTORY = Path("data/local/quiz-delivery-batches")

_DEFAULT_QUESTION_TYPES = (QuestionType.TRUE_FALSE, QuestionType.SINGLE_CHOICE)
_DEFAULT_COUNT_PER_TYPE = 3
_DEFAULT_COUNT_PER_CHAPTER = 1

BatchTarget = Literal["sub_chapter", "main_chapter"]


def run_quiz_batch_send(
    *,
    target: BatchTarget = "sub_chapter",
    question_types: Sequence[QuestionType] = _DEFAULT_QUESTION_TYPES,
    count_per_type: int = _DEFAULT_COUNT_PER_TYPE,
    count_per_chapter: int = _DEFAULT_COUNT_PER_CHAPTER,
    settings: Settings | None = None,
    generation_output_path: Path | None = None,
    delivery_output_path: Path | None = None,
) -> list[BeBatchResponse]:
    runtime_settings = settings or Settings()

    api_client = SpringQuizApiClient(
        base_url=runtime_settings.spring_internal_base_url,
        internal_token=runtime_settings.spring_internal_token.get_secret_value(),
    )
    generation_service = create_quiz_generation_service(runtime_settings)

    targets = api_client.find_targets()
    if target == "main_chapter":
        items = build_main_chapter_items_from_targets(targets, count_per_chapter)
    else:
        items = build_batch_items_from_targets(targets, question_types, count_per_type)

    if not items:
        raise ValueError("생성 대상 단원이 없습니다.")

    batch_run = QuizBatchService(generation_service).generate(items)
    write_jsonl(
        generation_output_path
        or (_GENERATION_OUTPUT_DIRECTORY / f"{batch_run.summary.batch_id}.jsonl"),
        batch_run.records,
    )

    responses = send_records_to_be(batch_run.records, api_client)
    write_jsonl(
        delivery_output_path
        or (_DELIVERY_OUTPUT_DIRECTORY / f"{batch_run.summary.batch_id}.jsonl"),
        responses,
    )

    return responses


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "생성 대상을 조회해 퀴즈를 생성하고 BE 배치 API로 전송합니다. "
            "실제 OpenAI 생성 호출과 BE 서버 전송이 함께 일어납니다."
        ),
    )
    parser.add_argument(
        "--target",
        dest="target",
        choices=["sub_chapter", "main_chapter"],
        default="sub_chapter",
        help=(
            "배치 대상 (기본: sub_chapter). "
            "main_chapter는 대단원별 SCENARIO 문항만 생성합니다."
        ),
    )
    parser.add_argument(
        "--question-types",
        dest="question_types",
        default=",".join(t.value for t in _DEFAULT_QUESTION_TYPES),
        help="쉼표로 구분한 문제 유형 목록 (기본: TRUE_FALSE,SINGLE_CHOICE, sub_chapter 대상에만 적용)",
    )
    parser.add_argument(
        "--count-per-type",
        dest="count_per_type",
        type=int,
        default=_DEFAULT_COUNT_PER_TYPE,
        help="소단원 하나당 유형별 생성 개수 (기본: 3, sub_chapter 대상에만 적용)",
    )
    parser.add_argument(
        "--count-per-chapter",
        dest="count_per_chapter",
        type=int,
        default=_DEFAULT_COUNT_PER_CHAPTER,
        help="대단원 하나당 시나리오 생성 개수 (기본: 1, main_chapter 대상에만 적용)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)
    question_types = [
        QuestionType(value.strip())
        for value in arguments.question_types.split(",")
        if value.strip()
    ]

    try:
        responses = run_quiz_batch_send(
            target=arguments.target,
            question_types=question_types,
            count_per_type=arguments.count_per_type,
            count_per_chapter=arguments.count_per_chapter,
        )
    except (httpx.HTTPError, ValidationError, ValueError, OSError) as error:
        print(
            json.dumps(
                {"stage": "quiz_batch_send", "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    summary = {
        "batches": len(responses),
        "total": sum(response.total for response in responses),
        "accepted": sum(response.accepted for response in responses),
        "rejected": sum(response.rejected for response in responses),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
