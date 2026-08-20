import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.application.search.evaluation import (
    evaluate_search_methods,
    load_search_evaluation_cases,
)
from app.application.search.evidence_quality import (
    evaluate_evidence_quality_for_topics,
)
from app.application.search.hybrid import HybridSearch
from app.application.search.index_health import (
    SearchIndexMismatchError,
    ensure_index_matches_corpus,
)
from app.core.config import Settings
from app.infrastructure.openai_embedding import OpenAIEmbeddingClient
from app.infrastructure.repositories.mysql_chunk import MySQLChunkRepository
from app.infrastructure.search.bm25 import BM25Search
from app.infrastructure.search.faiss import FaissVectorSearch
from app.infrastructure.tokenizers.kiwi import KiwiTokenizer

_DEFAULT_CASES_PATH = Path("data/local/evaluation/search_cases_v2.json")
_DEFAULT_OUTPUT_DIRECTORY = Path("data/local/evaluation")


def build_search_components(
    settings: Settings,
) -> tuple[MySQLChunkRepository, BM25Search, FaissVectorSearch, HybridSearch]:
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

    # 측정 결과가 신뢰할 수 없는 상태(재색인 필요)면 여기서 바로 중단한다.
    # 실제 서비스 기동 경로(quiz_mvp.create_quiz_generation_service)는 같은
    # 상황에서 경고만 남기고 계속 진행하지만, 품질 측정 도구는 정확한 일치가
    # 전제이므로 예외를 그대로 전파한다.
    ensure_index_matches_corpus(
        corpus_chunk_count=len(chunks),
        faiss_vector_count=faiss_search.vector_count,
    )

    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=chunk_repository,
    )

    return chunk_repository, bm25_search, faiss_search, hybrid_search


def run_search_quality_report(
    *,
    cases_path: Path,
    topics: Sequence[str] = (),
    k: int | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    runtime_settings = settings or Settings()
    resolved_k = k or runtime_settings.search_top_k

    _, bm25_search, faiss_search, hybrid_search = build_search_components(
        runtime_settings
    )
    cases = load_search_evaluation_cases(cases_path)

    def search_bm25(query: str, top_k: int) -> list[str]:
        return [
            result.chunk.chunk_key
            for result in bm25_search.search(query=query, top_k=top_k)
        ]

    def search_faiss(query: str, top_k: int) -> list[str]:
        return [
            result.chunk_key for result in faiss_search.search(query=query, top_k=top_k)
        ]

    def search_hybrid(query: str, top_k: int) -> list[str]:
        # HybridSearch는 query만 받고 settings.search_top_k만큼만 반환한다.
        # top_k가 그보다 크면 실제 운영에서 받는 결과 그대로 더 짧게 나온다.
        return [result.chunk.chunk_key for result in hybrid_search.search(query)][
            :top_k
        ]

    metrics_by_method = evaluate_search_methods(
        cases=cases,
        search_methods={
            "bm25": search_bm25,
            "faiss": search_faiss,
            "hybrid": search_hybrid,
        },
        k=resolved_k,
    )

    report: dict[str, object] = {
        "top_k": resolved_k,
        "evaluated_case_count": len(cases),
        "search_quality": {
            method_name: asdict(metrics)
            for method_name, metrics in metrics_by_method.items()
        },
    }

    if topics:
        retrieved_chunks_by_topic = {
            topic: [result.chunk for result in hybrid_search.search(topic)]
            for topic in topics
        }
        evidence_metrics = evaluate_evidence_quality_for_topics(
            retrieved_chunks_by_topic
        )
        report["evidence_quality"] = [asdict(metrics) for metrics in evidence_metrics]

    return report


def default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _DEFAULT_OUTPUT_DIRECTORY / f"search_quality_report_{timestamp}.json"


def write_report(
    output_path: Path,
    report: dict[str, object],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_topics(topics_path: Path | None) -> tuple[str, ...]:
    if topics_path is None:
        return ()

    data = json.loads(topics_path.read_text(encoding="utf-8"))

    if not isinstance(data, list) or not all(isinstance(topic, str) for topic in data):
        raise ValueError("topics 파일은 문자열 배열이어야 합니다.")

    return tuple(topic.strip() for topic in data if topic.strip())


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="현재 코퍼스 기준 BM25·FAISS·하이브리드 검색 품질을 측정합니다.",
    )
    parser.add_argument(
        "--cases",
        dest="cases_path",
        type=Path,
        default=_DEFAULT_CASES_PATH,
        help="검색 평가 케이스 JSON 파일 경로",
    )
    parser.add_argument(
        "--topics-file",
        dest="topics_path",
        type=Path,
        default=None,
        help="근거 품질을 진단할 topic 문자열 배열 JSON 파일 경로",
    )
    parser.add_argument(
        "--k",
        dest="k",
        type=int,
        default=None,
        help="평가할 상위 검색 결과 개수 (기본값: SEARCH_TOP_K 설정값)",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        default=None,
        help=(
            "결과 JSON 저장 경로 (기본값: "
            "data/local/evaluation/search_quality_report_<타임스탬프>.json)"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)

    try:
        topics = load_topics(arguments.topics_path)
        report = run_search_quality_report(
            cases_path=arguments.cases_path,
            topics=topics,
            k=arguments.k,
        )
    except (
        OSError,
        ValueError,
        FileNotFoundError,
        SearchIndexMismatchError,
    ) as error:
        print(
            json.dumps(
                {"error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    output_path = arguments.output_path or default_output_path()
    write_report(output_path, report)
    report["output_path"] = str(output_path)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
