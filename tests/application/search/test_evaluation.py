from pathlib import Path
from unittest.mock import Mock, call

import pytest

from app.application.search.evaluation import (
    calculate_recall_at_k,
    calculate_reciprocal_rank,
    evaluate_search_methods,
    evaluate_search_quality,
    load_search_evaluation_cases,
)
from app.domain.search import SearchEvaluationCase


def test_calculate_recall_at_k() -> None:
    case = SearchEvaluationCase(
        query="예금자보호제도란 무엇인가?",
        relevant_chunk_keys=(
            "chunk-10",
            "chunk-11",
        ),
    )

    recall = calculate_recall_at_k(
        case=case,
        retrieved_chunk_keys=(
            "chunk-10",
            "chunk-99",
            "chunk-11",
        ),
        k=2,
    )

    assert recall == 0.5


def test_return_zero_recall_when_relevant_chunk_is_not_retrieved() -> None:
    case = SearchEvaluationCase(
        query="예금자보호 한도는 얼마인가?",
        relevant_chunk_keys=("chunk-10",),
    )

    recall = calculate_recall_at_k(
        case=case,
        retrieved_chunk_keys=(
            "chunk-20",
            "chunk-21",
            "chunk-22",
        ),
        k=3,
    )

    assert recall == 0.0


def test_return_full_recall_when_all_relevant_chunks_are_retrieved() -> None:
    case = SearchEvaluationCase(
        query="예금자보호제도의 적용 범위는?",
        relevant_chunk_keys=(
            "chunk-10",
            "chunk-11",
        ),
    )

    recall = calculate_recall_at_k(
        case=case,
        retrieved_chunk_keys=(
            "chunk-10",
            "chunk-11",
            "chunk-99",
        ),
        k=3,
    )

    assert recall == 1.0


def test_reject_k_less_than_one() -> None:
    case = SearchEvaluationCase(
        query="예금이란 무엇인가?",
        relevant_chunk_keys=("chunk-10",),
    )

    with pytest.raises(
        ValueError,
        match="평가할 상위 검색 결과 개수는 1 이상이어야 합니다.",
    ):
        calculate_recall_at_k(
            case=case,
            retrieved_chunk_keys=("chunk-10",),
            k=0,
        )


def test_reject_evaluation_case_without_relevant_chunk_keys() -> None:
    case = SearchEvaluationCase(
        query="예금이란 무엇인가?",
        relevant_chunk_keys=(),
    )

    with pytest.raises(
        ValueError,
        match="평가 케이스에는 정답 청크 키가 하나 이상 필요합니다.",
    ):
        calculate_recall_at_k(
            case=case,
            retrieved_chunk_keys=("chunk-10",),
            k=5,
        )


def test_calculate_reciprocal_rank() -> None:
    case = SearchEvaluationCase(
        query="예금자보호제도란 무엇인가?",
        relevant_chunk_keys=("chunk-10",),
    )

    reciprocal_rank = calculate_reciprocal_rank(
        case=case,
        retrieved_chunk_keys=(
            "chunk-99",
            "chunk-10",
            "chunk-11",
        ),
        k=3,
    )

    assert reciprocal_rank == 0.5


def test_return_zero_reciprocal_rank_when_relevant_chunk_is_not_retrieved() -> None:
    case = SearchEvaluationCase(
        query="예금자보호제도란 무엇인가?",
        relevant_chunk_keys=("chunk-10",),
    )

    reciprocal_rank = calculate_reciprocal_rank(
        case=case,
        retrieved_chunk_keys=(
            "chunk-20",
            "chunk-21",
            "chunk-22",
        ),
        k=3,
    )

    assert reciprocal_rank == 0.0


def test_evaluate_search_quality() -> None:
    cases = (
        SearchEvaluationCase(
            query="첫 번째 질문",
            relevant_chunk_keys=("chunk-1",),
        ),
        SearchEvaluationCase(
            query="두 번째 질문",
            relevant_chunk_keys=(
                "chunk-2",
                "chunk-3",
            ),
        ),
    )

    metrics = evaluate_search_quality(
        cases=cases,
        retrieved_chunk_keys_by_case=(
            (
                "chunk-1",
                "chunk-9",
            ),
            (
                "chunk-9",
                "chunk-2",
            ),
        ),
        k=2,
    )

    assert metrics.top_k == 2
    assert metrics.evaluated_case_count == 2
    assert metrics.recall_at_k == pytest.approx(0.75)
    assert metrics.mean_reciprocal_rank == pytest.approx(0.75)


def test_reject_empty_search_evaluation_cases() -> None:
    with pytest.raises(
        ValueError,
        match="검색 품질을 평가할 케이스가 하나 이상 필요합니다.",
    ):
        evaluate_search_quality(
            cases=(),
            retrieved_chunk_keys_by_case=(),
            k=5,
        )


def test_reject_mismatched_case_and_search_result_counts() -> None:
    cases = (
        SearchEvaluationCase(
            query="예금이란 무엇인가?",
            relevant_chunk_keys=("deposit:0",),
        ),
    )

    with pytest.raises(
        ValueError,
        match="평가 케이스 수와 검색 결과 목록 수가 일치해야 합니다.",
    ):
        evaluate_search_quality(
            cases=cases,
            retrieved_chunk_keys_by_case=(),
            k=5,
        )


def test_load_search_evaluation_cases(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "search_cases.json"
    file_path.write_text(
        """
[
  {
    "query": "예금이란 무엇인가?",
    "relevant_chunk_keys": ["deposit:0", "deposit:1"]
  }
]
""".strip(),
        encoding="utf-8",
    )

    cases = load_search_evaluation_cases(file_path)

    assert cases == (
        SearchEvaluationCase(
            query="예금이란 무엇인가?",
            relevant_chunk_keys=(
                "deposit:0",
                "deposit:1",
            ),
        ),
    )


def test_reject_invalid_search_evaluation_data(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "invalid_search_cases.json"
    file_path.write_text(
        """
[
  {
    "query": "",
    "relevant_chunk_keys": ["deposit:0"]
  }
]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="검색 평가 질문은 비어 있을 수 없습니다.",
    ):
        load_search_evaluation_cases(file_path)


def test_evaluate_same_cases_with_multiple_search_methods() -> None:
    cases = (
        SearchEvaluationCase(
            query="예금이란 무엇인가?",
            relevant_chunk_keys=("deposit:0",),
        ),
        SearchEvaluationCase(
            query="주식이란 무엇인가?",
            relevant_chunk_keys=("stock:0",),
        ),
    )

    bm25_search = Mock(
        side_effect=[
            ("deposit:0",),
            ("stock:0",),
        ]
    )
    faiss_search = Mock(
        side_effect=[
            (
                "other:0",
                "deposit:0",
            ),
            ("other:0",),
        ]
    )
    hybrid_search = Mock(
        side_effect=[
            ("deposit:0",),
            ("stock:0",),
        ]
    )

    metrics_by_method = evaluate_search_methods(
        cases=cases,
        search_methods={
            "bm25": bm25_search,
            "faiss": faiss_search,
            "hybrid": hybrid_search,
        },
        k=2,
    )

    assert metrics_by_method["bm25"].recall_at_k == pytest.approx(1.0)
    assert metrics_by_method["faiss"].recall_at_k == pytest.approx(0.5)
    assert metrics_by_method["faiss"].mean_reciprocal_rank == pytest.approx(0.25)
    assert metrics_by_method["hybrid"].recall_at_k == pytest.approx(1.0)

    expected_calls = [
        call("예금이란 무엇인가?", 2),
        call("주식이란 무엇인가?", 2),
    ]
    assert bm25_search.call_args_list == expected_calls
    assert faiss_search.call_args_list == expected_calls
    assert hybrid_search.call_args_list == expected_calls
