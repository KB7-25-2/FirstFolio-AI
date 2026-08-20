from unittest.mock import Mock

import pytest

from app.application.ports.chunk_repository import ChunkNotFoundError
from app.application.search.hybrid import HybridSearch
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.search import SearchResult, VectorSearchResult
from app.infrastructure.repositories.in_memory_chunk import (
    InMemoryChunkRepository,
)


def create_chunk(
    document_id: str,
    title: str,
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_key=f"{document_id}:0",
        sequence=0,
        content=f"{title} 설명",
        title=title,
        source=f"{document_id}.txt",
    )


def test_combine_bm25_and_faiss_results_by_chunk_key() -> None:
    deposit_chunk = create_chunk("deposit", "예금")
    stock_chunk = create_chunk("stock", "주식")
    bond_chunk = create_chunk("bond", "채권")

    bm25_search = Mock()
    bm25_search.search.return_value = [
        SearchResult(
            chunk=deposit_chunk,
            score=10.0,
        ),
        SearchResult(
            chunk=stock_chunk,
            score=5.0,
        ),
    ]

    faiss_search = Mock()
    faiss_search.search.return_value = [
        VectorSearchResult(
            chunk_key="deposit:0",
            score=0.95,
        ),
        VectorSearchResult(
            chunk_key="bond:0",
            score=0.80,
        ),
    ]

    repository = InMemoryChunkRepository()
    repository.save_all(
        [
            deposit_chunk,
            stock_chunk,
            bond_chunk,
        ]
    )

    settings = Settings(
        search_top_k=5,
        search_candidate_top_k=5,
        search_rrf_k=1,
        bm25_weight=0.7,
        faiss_weight=0.3,
        _env_file=None,
    )
    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=repository,
    )

    results = hybrid_search.search("안전하게 돈을 맡기기")

    # rrf_k=1: bm25 deposit=0.7/2, stock=0.7/3 / faiss deposit=0.3/2, bond=0.3/3
    assert [result.chunk.chunk_key for result in results] == [
        "deposit:0",
        "stock:0",
        "bond:0",
    ]
    assert [result.score for result in results] == pytest.approx(
        [
            0.7 / 2 + 0.3 / 2,
            0.7 / 3,
            0.3 / 3,
        ]
    )
    bm25_search.search.assert_called_once_with(
        query="안전하게 돈을 맡기기",
        top_k=5,
    )
    faiss_search.search.assert_called_once_with(
        query="안전하게 돈을 맡기기",
        top_k=5,
    )


def test_search_candidate_pool_can_exceed_final_top_k() -> None:
    deposit_chunk = create_chunk("deposit", "예금")

    bm25_search = Mock()
    bm25_search.search.return_value = [
        SearchResult(
            chunk=deposit_chunk,
            score=10.0,
        )
    ]

    faiss_search = Mock()
    faiss_search.search.return_value = []

    repository = InMemoryChunkRepository()
    repository.save_all([deposit_chunk])

    settings = Settings(
        search_top_k=5,
        search_candidate_top_k=20,
        search_rrf_k=60,
        bm25_weight=0.7,
        faiss_weight=0.3,
        _env_file=None,
    )
    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=repository,
    )

    hybrid_search.search("예금")

    bm25_search.search.assert_called_once_with(
        query="예금",
        top_k=20,
    )
    faiss_search.search.assert_called_once_with(
        query="예금",
        top_k=20,
    )


def test_skip_faiss_search_when_faiss_weight_is_zero() -> None:
    deposit_chunk = create_chunk("deposit", "예금")

    bm25_search = Mock()
    bm25_search.search.return_value = [
        SearchResult(
            chunk=deposit_chunk,
            score=10.0,
        )
    ]

    faiss_search = Mock()
    repository = InMemoryChunkRepository()

    settings = Settings(
        search_top_k=5,
        search_candidate_top_k=5,
        search_rrf_k=1,
        bm25_weight=1.0,
        faiss_weight=0.0,
        _env_file=None,
    )
    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=repository,
    )

    results = hybrid_search.search("예금")

    assert [result.chunk.chunk_key for result in results] == [
        "deposit:0",
    ]
    assert results[0].score == pytest.approx(1.0 / 2)
    bm25_search.search.assert_called_once_with(
        query="예금",
        top_k=5,
    )
    faiss_search.search.assert_not_called()


def test_skip_bm25_search_when_bm25_weight_is_zero() -> None:
    deposit_chunk = create_chunk("deposit", "예금")

    bm25_search = Mock()

    faiss_search = Mock()
    faiss_search.search.return_value = [
        VectorSearchResult(
            chunk_key="deposit:0",
            score=0.95,
        )
    ]

    repository = InMemoryChunkRepository()
    repository.save_all([deposit_chunk])

    settings = Settings(
        search_top_k=5,
        search_candidate_top_k=5,
        search_rrf_k=1,
        bm25_weight=0.0,
        faiss_weight=1.0,
        _env_file=None,
    )
    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=repository,
    )

    results = hybrid_search.search("안전한 금융상품")

    assert [result.chunk.chunk_key for result in results] == [
        "deposit:0",
    ]
    assert results[0].score == pytest.approx(1.0 / 2)
    bm25_search.search.assert_not_called()
    faiss_search.search.assert_called_once_with(
        query="안전한 금융상품",
        top_k=5,
    )


def test_limit_combined_results_to_search_top_k() -> None:
    deposit_chunk = create_chunk("deposit", "예금")
    stock_chunk = create_chunk("stock", "주식")
    bond_chunk = create_chunk("bond", "채권")
    fund_chunk = create_chunk("fund", "펀드")

    bm25_search = Mock()
    bm25_search.search.return_value = [
        SearchResult(
            chunk=deposit_chunk,
            score=10.0,
        ),
        SearchResult(
            chunk=stock_chunk,
            score=5.0,
        ),
    ]

    faiss_search = Mock()
    faiss_search.search.return_value = [
        VectorSearchResult(
            chunk_key="bond:0",
            score=0.95,
        ),
        VectorSearchResult(
            chunk_key="fund:0",
            score=0.80,
        ),
    ]

    repository = InMemoryChunkRepository()
    repository.save_all(
        [
            bond_chunk,
            fund_chunk,
        ]
    )

    settings = Settings(
        search_top_k=2,
        search_candidate_top_k=5,
        search_rrf_k=1,
        bm25_weight=0.7,
        faiss_weight=0.3,
        _env_file=None,
    )
    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=repository,
    )

    results = hybrid_search.search("금융상품")

    assert [result.chunk.chunk_key for result in results] == [
        "deposit:0",
        "stock:0",
    ]
    assert len(results) == 2


def test_raise_error_when_faiss_chunk_key_does_not_exist() -> None:
    bm25_search = Mock()
    bm25_search.search.return_value = []

    faiss_search = Mock()
    faiss_search.search.return_value = [
        VectorSearchResult(
            chunk_key="missing:0",
            score=0.95,
        )
    ]

    repository = InMemoryChunkRepository()

    settings = Settings(
        search_top_k=5,
        search_candidate_top_k=5,
        search_rrf_k=1,
        bm25_weight=0.7,
        faiss_weight=0.3,
        _env_file=None,
    )
    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=repository,
    )

    with pytest.raises(
        ChunkNotFoundError,
        match="요청한 청크를 찾을 수 없습니다: missing:0",
    ):
        hybrid_search.search("존재하지 않는 청크")


def test_return_empty_list_when_both_searches_have_no_results() -> None:
    bm25_search = Mock()
    bm25_search.search.return_value = []

    faiss_search = Mock()
    faiss_search.search.return_value = []

    repository = InMemoryChunkRepository()

    settings = Settings(
        search_top_k=5,
        search_candidate_top_k=5,
        search_rrf_k=1,
        bm25_weight=0.7,
        faiss_weight=0.3,
        _env_file=None,
    )
    hybrid_search = HybridSearch(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=repository,
    )

    results = hybrid_search.search("검색되지 않는 질문")

    assert results == []
    bm25_search.search.assert_called_once_with(
        query="검색되지 않는 질문",
        top_k=5,
    )
    faiss_search.search.assert_called_once_with(
        query="검색되지 않는 질문",
        top_k=5,
    )
