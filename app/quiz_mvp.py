import argparse
import json
import sys
from collections.abc import Sequence

from app.application.quiz_generation import (
    QuizGenerationService,
    QuizGenerationValidationError,
)
from app.application.search.hybrid import HybridSearch
from app.core.config import Settings
from app.domain.quiz import QuestionType, QuizGenerationResult
from app.infrastructure.openai_embedding import OpenAIEmbeddingClient
from app.infrastructure.openai_quiz import OpenAIQuizModelClient
from app.infrastructure.repositories.mysql_chunk import MySQLChunkRepository
from app.infrastructure.search.bm25 import BM25Search
from app.infrastructure.search.faiss import FaissVectorSearch
from app.infrastructure.tokenizers.kiwi import KiwiTokenizer

_QUESTION_TYPE_BY_ARGUMENT = {
    "true_false": QuestionType.TRUE_FALSE,
    "single_choice": QuestionType.SINGLE_CHOICE,
    "scenario": QuestionType.SCENARIO,
}


def create_quiz_generation_service(
    settings: Settings,
) -> QuizGenerationService:
    chunk_repository = MySQLChunkRepository(settings)
    chunks = chunk_repository.find_all()
    bm25_search = BM25Search(
        chunks=chunks,
        tokenizer=KiwiTokenizer(),
    )
    embedding_client = OpenAIEmbeddingClient(
        model=settings.embedding_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    faiss_search = FaissVectorSearch.load(
        index_path=settings.faiss_index_path,
        mapping_path=settings.faiss_mapping_path,
        embedding_client=embedding_client,
    )
    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=chunk_repository,
    )
    model_client = OpenAIQuizModelClient(
        model=settings.generation_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )

    return QuizGenerationService(
        settings=settings,
        hybrid_search=hybrid_search,
        chunk_repository=chunk_repository,
        model_client=model_client,
    )


def generate_quiz_mvp(
    *,
    quiz_type: str,
    topic: str,
    settings: Settings | None = None,
) -> QuizGenerationResult:
    question_type = _QUESTION_TYPE_BY_ARGUMENT.get(quiz_type)

    if question_type is None:
        raise ValueError(f"지원하지 않는 퀴즈 유형입니다: {quiz_type}")

    runtime_settings = settings or Settings()
    service = create_quiz_generation_service(runtime_settings)

    return service.generate(
        question_type=question_type,
        topic=topic,
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="근거 기반 금융교육 퀴즈 MVP를 실행합니다.",
    )
    parser.add_argument(
        "--type",
        dest="quiz_type",
        required=True,
        choices=tuple(_QUESTION_TYPE_BY_ARGUMENT),
        help="퀴즈 유형",
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="검색 및 퀴즈 생성에 사용할 금융 주제",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
) -> int:
    arguments = build_argument_parser().parse_args(argv)

    try:
        result = generate_quiz_mvp(
            quiz_type=arguments.quiz_type,
            topic=arguments.topic,
        )
    except QuizGenerationValidationError as error:
        print(
            json.dumps(
                {
                    "errors": list(error.errors),
                    "diagnostics": {
                        "stage": error.stage,
                        "reason": error.reason,
                        "unsupported_claims": list(error.unsupported_claims),
                    },
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
