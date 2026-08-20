import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.application.newsletter_collection import (
    collect_week_news_chunks,
    select_top_issue_candidates,
)
from app.application.newsletter_generation import (
    NewsletterDraftGenerationError,
    NewsletterGenerationService,
    generate_newsletter_draft,
)
from app.application.ports.chunk_repository import ChunkRepository
from app.core.config import Settings
from app.domain.newsletter import REQUIRED_SECTION_SIZE, NewsletterDeliveryResponse
from app.infrastructure.openai_newsletter import OpenAINewsletterModelClient
from app.infrastructure.repositories.mysql_chunk import MySQLChunkRepository
from app.infrastructure.spring_quiz_api_client import SpringQuizApiClient
from app.quiz_batch_dry_run import write_jsonl

_GENERATION_OUTPUT_DIRECTORY = Path("data/local/newsletter-generation-batches")
_DEFAULT_CANDIDATE_COUNT = 5
"""이슈 선정 후보 개수. 필요한 3개보다 여유를 둬서 grounding 실패를 대비한다."""


def this_monday(today: date) -> date:
    return today - timedelta(days=today.weekday())


def create_newsletter_generation_service(
    settings: Settings,
    chunk_repository: ChunkRepository,
) -> NewsletterGenerationService:
    model_client = OpenAINewsletterModelClient(
        model=settings.generation_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    return NewsletterGenerationService(
        settings=settings,
        chunk_repository=chunk_repository,
        model_client=model_client,
    )


def run_newsletter_batch_send(
    *,
    week_start_date: date | None = None,
    candidate_count: int = _DEFAULT_CANDIDATE_COUNT,
    settings: Settings | None = None,
    generation_output_path: Path | None = None,
) -> NewsletterDeliveryResponse:
    runtime_settings = settings or Settings()
    resolved_week_start_date = week_start_date or this_monday(date.today())

    api_client = SpringQuizApiClient(
        base_url=runtime_settings.spring_internal_base_url,
        internal_token=runtime_settings.spring_internal_token.get_secret_value(),
    )
    chunk_repository = MySQLChunkRepository(runtime_settings)
    all_chunks = chunk_repository.find_all()
    week_chunks = collect_week_news_chunks(all_chunks, resolved_week_start_date)
    candidates = select_top_issue_candidates(week_chunks, count=candidate_count)

    if len(candidates) < REQUIRED_SECTION_SIZE:
        raise ValueError(
            f"{resolved_week_start_date.isoformat()} 주간 뉴스레터 이슈 후보가 "
            f"부족합니다 (필요: {REQUIRED_SECTION_SIZE}, 확보: {len(candidates)})."
        )

    generation_service = create_newsletter_generation_service(
        runtime_settings, chunk_repository
    )
    draft_result = generate_newsletter_draft(
        generation_service, candidates, resolved_week_start_date
    )

    write_jsonl(
        generation_output_path or (_GENERATION_OUTPUT_DIRECTORY / f"{uuid4()}.jsonl"),
        [draft_result.draft],
    )

    return api_client.send_newsletter(draft_result.draft)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "이번 주 뉴스로 주간 뉴스레터를 생성해 BE 내부 API로 전송합니다. "
            "실제 OpenAI 생성 호출과 BE 서버 전송이 함께 일어납니다."
        ),
    )
    parser.add_argument(
        "--week-start-date",
        dest="week_start_date",
        default=None,
        help="대상 주 월요일 (YYYY-MM-DD, 기본값: 실행 시점 기준 이번 주 월요일)",
    )
    parser.add_argument(
        "--candidate-count",
        dest="candidate_count",
        type=int,
        default=_DEFAULT_CANDIDATE_COUNT,
        help=f"이슈 선정 후보 개수 (기본: {_DEFAULT_CANDIDATE_COUNT})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)
    week_start_date = (
        date.fromisoformat(arguments.week_start_date)
        if arguments.week_start_date
        else None
    )

    try:
        response = run_newsletter_batch_send(
            week_start_date=week_start_date,
            candidate_count=arguments.candidate_count,
        )
    except (
        httpx.HTTPError,
        ValidationError,
        ValueError,
        OSError,
        NewsletterDraftGenerationError,
    ) as error:
        print(
            json.dumps(
                {"stage": "newsletter_batch_send", "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "newsletter_id": response.newsletter_id,
                "week_start_date": response.week_start_date.isoformat(),
                "status": response.status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
