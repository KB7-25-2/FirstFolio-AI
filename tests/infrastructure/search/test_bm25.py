import pytest

from app.domain.chunk import DocumentChunk
from app.infrastructure.search.bm25 import BM25Search
from app.infrastructure.tokenizers.kiwi import KiwiTokenizer


@pytest.fixture(scope="module")
def tokenizer() -> KiwiTokenizer:
    return KiwiTokenizer()


@pytest.fixture(scope="module")
def bm25_search(
    tokenizer: KiwiTokenizer,
) -> BM25Search:
    chunks = [
        DocumentChunk(
            sequence=0,
            content="예금은 돈을 맡기고 금리를 받는 금융상품이다.",
            title="예금",
            source="deposit.txt",
        ),
        DocumentChunk(
            sequence=1,
            content="주식은 기업의 지분을 나타내는 금융상품이다.",
            title="주식",
            source="stock.txt",
        ),
        DocumentChunk(
            sequence=2,
            content="채권은 발행자에게 돈을 빌려주고 이자를 받는 상품이다.",
            title="채권",
            source="bond.txt",
        ),
        DocumentChunk(
            sequence=3,
            content="펀드는 여러 자산에 분산 투자하는 상품이다.",
            title="펀드",
            source="fund.txt",
        ),
    ]

    return BM25Search(
        chunks=chunks,
        tokenizer=tokenizer,
    )


def test_search_relevant_chunk_first(
    bm25_search: BM25Search,
) -> None:
    results = bm25_search.search(
        query="예금 금리",
        top_k=3,
    )

    assert results
    assert results[0].chunk.title == "예금"
    assert results[0].score > 0


def test_limit_search_results(
    bm25_search: BM25Search,
) -> None:
    results = bm25_search.search(
        query="예금 채권",
        top_k=1,
    )

    assert len(results) == 1


@pytest.mark.parametrize(
    "query",
    [
        "",
        "부동산 임대",
    ],
)
def test_return_empty_results_for_unsearchable_query(
    bm25_search: BM25Search,
    query: str,
) -> None:
    assert bm25_search.search(query=query, top_k=3) == []


def test_reject_invalid_top_k(
    bm25_search: BM25Search,
) -> None:
    with pytest.raises(
        ValueError,
        match="1 이상",
    ):
        bm25_search.search(
            query="예금",
            top_k=0,
        )


def test_reject_empty_chunk_collection(
    tokenizer: KiwiTokenizer,
) -> None:
    with pytest.raises(
        ValueError,
        match="문서 청크가 없습니다",
    ):
        BM25Search(
            chunks=[],
            tokenizer=tokenizer,
        )


def test_reject_chunk_collection_without_search_tokens(
    tokenizer: KiwiTokenizer,
) -> None:
    chunks = [
        DocumentChunk(
            sequence=0,
            content="... !!!",
            title="문장부호",
            source="punctuation.txt",
        )
    ]

    with pytest.raises(
        ValueError,
        match="검색 토큰이 없습니다",
    ):
        BM25Search(
            chunks=chunks,
            tokenizer=tokenizer,
        )
