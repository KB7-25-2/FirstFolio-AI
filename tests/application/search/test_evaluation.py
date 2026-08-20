from pathlib import Path
from unittest.mock import Mock, call

import pytest

from app.application.search.evaluation import (
    calculate_recall_at_k,
    calculate_reciprocal_rank,
    evaluate_search_methods,
    evaluate_search_quality,
    find_chunk_key_by_text,
    load_search_evaluation_cases,
)
from app.domain.chunk import DocumentChunk
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


def test_load_search_evaluation_cases_with_relevant_text(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "search_cases_with_text.json"
    file_path.write_text(
        """
[
  {
    "query": "가처분소득은 어떻게 산출하는가?",
    "relevant_chunk_keys": ["83:20"],
    "relevant_text": "가처분소득은 개인소득에서 세금을 뺀 것이다."
  },
  {
    "query": "예금이란 무엇인가?",
    "relevant_chunk_keys": ["deposit:0"]
  }
]
""".strip(),
        encoding="utf-8",
    )

    cases = load_search_evaluation_cases(file_path)

    assert cases == (
        SearchEvaluationCase(
            query="가처분소득은 어떻게 산출하는가?",
            relevant_chunk_keys=("83:20",),
            relevant_text="가처분소득은 개인소득에서 세금을 뺀 것이다.",
        ),
        SearchEvaluationCase(
            query="예금이란 무엇인가?",
            relevant_chunk_keys=("deposit:0",),
        ),
    )


def test_reject_blank_relevant_text(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "blank_relevant_text.json"
    file_path.write_text(
        """
[
  {
    "query": "예금이란 무엇인가?",
    "relevant_chunk_keys": ["deposit:0"],
    "relevant_text": "   "
  }
]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="relevant_text를 지정하면 비어 있지 않은 문자열이어야 합니다.",
    ):
        load_search_evaluation_cases(file_path)


def test_find_chunk_key_by_text_matches_normalized_whitespace() -> None:
    chunks = [
        DocumentChunk(
            document_id="83",
            chunk_key="83:20",
            sequence=20,
            content="가처분소득은  개인소득에서\n세금을 뺀 것이다.",
            title="금융 교과서",
            source="83.txt",
        ),
        DocumentChunk(
            document_id="83",
            chunk_key="83:21",
            sequence=21,
            content="당좌비율은 유동부채 대비 당좌자산의 비율이다.",
            title="금융 교과서",
            source="83.txt",
        ),
    ]

    chunk_key = find_chunk_key_by_text(
        chunks,
        "가처분소득은 개인소득에서 세금을 뺀 것이다.",
    )

    assert chunk_key == "83:20"


def test_find_chunk_key_by_text_returns_none_when_no_match() -> None:
    chunks = [
        DocumentChunk(
            document_id="83",
            chunk_key="83:21",
            sequence=21,
            content="당좌비율은 유동부채 대비 당좌자산의 비율이다.",
            title="금융 교과서",
            source="83.txt",
        ),
    ]

    chunk_key = find_chunk_key_by_text(
        chunks,
        "여기 없는 문장이다.",
    )

    assert chunk_key is None


def test_reject_blank_search_text_for_chunk_key_lookup() -> None:
    with pytest.raises(
        ValueError,
        match="검색할 정답 문장은 비어 있을 수 없습니다.",
    ):
        find_chunk_key_by_text([], "   ")


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
