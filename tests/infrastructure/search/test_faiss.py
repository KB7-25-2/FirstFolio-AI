import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.domain.chunk import DocumentChunk
from app.infrastructure.search.faiss import FaissVectorSearch


class ControlledEmbeddingClient:
    def __init__(
        self,
        vectors_by_text: dict[str, list[float]],
    ) -> None:
        self._vectors_by_text = vectors_by_text

    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [self._vectors_by_text[text] for text in texts]

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        return self._vectors_by_text[text]


def create_vector_search() -> FaissVectorSearch:
    chunks = [
        DocumentChunk(
            document_id="deposit",
            chunk_key="deposit:0",
            sequence=0,
            content="예금",
            title="예금",
            source="deposit.txt",
        ),
        DocumentChunk(
            document_id="stock",
            chunk_key="stock:0",
            sequence=0,
            content="주식",
            title="주식",
            source="stock.txt",
        ),
        DocumentChunk(
            document_id="bond",
            chunk_key="bond:0",
            sequence=0,
            content="채권",
            title="채권",
            source="bond.txt",
        ),
    ]
    embedding_client = ControlledEmbeddingClient(
        {
            "예금": [1.0, 0.0, 0.0],
            "주식": [0.0, 1.0, 0.0],
            "채권": [0.0, 0.0, 1.0],
            "안전하게 돈을 맡기기": [0.9, 0.1, 0.0],
        }
    )

    return FaissVectorSearch(
        chunks=chunks,
        embedding_client=embedding_client,
    )


def test_search_similar_vector_first() -> None:
    vector_search = create_vector_search()

    results = vector_search.search(
        query="안전하게 돈을 맡기기",
        top_k=2,
    )

    assert len(results) == 2
    assert results[0].chunk_key == "deposit:0"
    assert results[1].chunk_key == "stock:0"
    assert results[0].score > results[1].score


def test_limit_results_to_stored_vector_count() -> None:
    vector_search = create_vector_search()

    results = vector_search.search(
        query="안전하게 돈을 맡기기",
        top_k=5,
    )

    assert len(results) == 3


def test_return_empty_results_for_empty_query() -> None:
    vector_search = create_vector_search()

    assert vector_search.search(query="   ", top_k=3) == []


def test_reject_invalid_top_k() -> None:
    vector_search = create_vector_search()

    with pytest.raises(
        ValueError,
        match="1 이상",
    ):
        vector_search.search(
            query="안전하게 돈을 맡기기",
            top_k=0,
        )


def test_reject_empty_chunk_collection() -> None:
    embedding_client = ControlledEmbeddingClient({})

    with pytest.raises(
        ValueError,
        match="문서 청크가 없습니다",
    ):
        FaissVectorSearch(
            chunks=[],
            embedding_client=embedding_client,
        )


def create_validation_chunks() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            document_id="deposit",
            chunk_key="deposit:0",
            sequence=0,
            content="예금",
            title="예금",
            source="deposit.txt",
        ),
        DocumentChunk(
            document_id="stock",
            chunk_key="stock:0",
            sequence=0,
            content="주식",
            title="주식",
            source="stock.txt",
        ),
    ]


def test_reject_mismatched_chunk_and_embedding_count() -> None:
    embedding_client = Mock()
    embedding_client.embed_documents.return_value = [
        [1.0, 0.0, 0.0],
    ]

    with pytest.raises(
        ValueError,
        match="청크 수와 임베딩 벡터 수",
    ):
        FaissVectorSearch(
            chunks=create_validation_chunks(),
            embedding_client=embedding_client,
        )


def test_reject_inconsistent_embedding_dimensions() -> None:
    embedding_client = ControlledEmbeddingClient(
        {
            "예금": [1.0, 0.0, 0.0],
            "주식": [0.0, 1.0],
        }
    )

    with pytest.raises(
        ValueError,
        match="벡터의 차원이 같아야",
    ):
        FaissVectorSearch(
            chunks=create_validation_chunks(),
            embedding_client=embedding_client,
        )


def test_reject_zero_embedding_vector() -> None:
    embedding_client = ControlledEmbeddingClient(
        {
            "예금": [0.0, 0.0, 0.0],
        }
    )

    with pytest.raises(
        ValueError,
        match="크기가 0인 임베딩 벡터",
    ):
        FaissVectorSearch(
            chunks=create_validation_chunks()[:1],
            embedding_client=embedding_client,
        )


def test_reject_query_embedding_with_different_dimension() -> None:
    embedding_client = Mock()
    embedding_client.embed_documents.return_value = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    embedding_client.embed_query.return_value = [1.0, 0.0]

    vector_search = FaissVectorSearch(
        chunks=create_validation_chunks(),
        embedding_client=embedding_client,
    )

    with pytest.raises(
        ValueError,
        match="벡터 차원이 일치하지 않습니다",
    ):
        vector_search.search(
            query="예금 검색",
            top_k=1,
        )


def test_save_load_and_search_same_results(
    tmp_path: Path,
) -> None:
    vector_search = create_vector_search()
    index_path = tmp_path / "indexes" / "financial.faiss"
    mapping_path = tmp_path / "indexes" / "financial.json"

    vector_search.save(
        index_path=index_path,
        mapping_path=mapping_path,
    )

    assert index_path.is_file()
    assert mapping_path.is_file()

    mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))
    assert mapping_data == {
        "chunk_keys": [
            "deposit:0",
            "stock:0",
            "bond:0",
        ]
    }

    embedding_client = ControlledEmbeddingClient(
        {
            "안전하게 돈을 맡기기": [0.9, 0.1, 0.0],
        }
    )
    loaded_search = FaissVectorSearch.load(
        index_path=index_path,
        mapping_path=mapping_path,
        embedding_client=embedding_client,
    )

    original_results = vector_search.search(
        query="안전하게 돈을 맡기기",
        top_k=2,
    )
    loaded_results = loaded_search.search(
        query="안전하게 돈을 맡기기",
        top_k=2,
    )

    assert [result.chunk_key for result in loaded_results] == [
        result.chunk_key for result in original_results
    ]
    assert [result.score for result in loaded_results] == pytest.approx(
        [result.score for result in original_results]
    )


def test_reject_mismatched_index_and_chunk_key_count(
    tmp_path: Path,
) -> None:
    vector_search = create_vector_search()
    index_path = tmp_path / "financial.faiss"
    mapping_path = tmp_path / "financial.json"

    vector_search.save(
        index_path=index_path,
        mapping_path=mapping_path,
    )
    mapping_path.write_text(
        json.dumps(
            {
                "chunk_keys": [
                    "deposit:0",
                ]
            }
        ),
        encoding="utf-8",
    )

    embedding_client = ControlledEmbeddingClient({})

    with pytest.raises(
        ValueError,
        match="벡터 수와 청크 키 수가 일치하지 않습니다",
    ):
        FaissVectorSearch.load(
            index_path=index_path,
            mapping_path=mapping_path,
            embedding_client=embedding_client,
        )


def test_reject_missing_index_or_mapping_file(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "financial.faiss"
    mapping_path = tmp_path / "financial.json"
    embedding_client = ControlledEmbeddingClient({})

    with pytest.raises(
        FileNotFoundError,
        match="인덱스 파일을 찾을 수 없습니다",
    ):
        FaissVectorSearch.load(
            index_path=index_path,
            mapping_path=mapping_path,
            embedding_client=embedding_client,
        )

    vector_search = create_vector_search()
    vector_search.save(
        index_path=index_path,
        mapping_path=mapping_path,
    )
    mapping_path.unlink()

    with pytest.raises(
        FileNotFoundError,
        match="매핑 파일을 찾을 수 없습니다",
    ):
        FaissVectorSearch.load(
            index_path=index_path,
            mapping_path=mapping_path,
            embedding_client=embedding_client,
        )
