import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from app.application.search.faiss_pipeline import (
    FaissIndexNotBuiltError,
    FaissSearchPipeline,
)
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.infrastructure.repositories.in_memory_chunk import InMemoryChunkRepository


def _chunk(
    document_id: str,
    sequence: int,
    content: str,
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_key=f"{document_id}:{sequence}",
        sequence=sequence,
        content=content,
        title=f"문서 {document_id}",
        source=f"{document_id}.txt",
    )


def _pipeline(
    repository: InMemoryChunkRepository,
    top_k: int = 5,
) -> FaissSearchPipeline:
    return FaissSearchPipeline(
        settings=Settings(
            search_top_k=top_k,
            _env_file=None,
        ),
        chunk_repository=repository,
        embedding_client=DeterministicFakeEmbedding(size=8),
    )


def test_rebuild_index_and_search_repository_chunks() -> None:
    repository = InMemoryChunkRepository()
    repository.save_all(
        [
            _chunk("1", 0, "예금은 금리를 제공한다."),
            _chunk("1", 1, "채권은 만기와 이자를 가진다."),
            _chunk("2", 0, "주식은 기업의 지분을 나타낸다."),
        ]
    )
    pipeline = _pipeline(repository)

    indexed_chunk_count = pipeline.rebuild_index()
    results = pipeline.search("예금은 금리를 제공한다.")

    assert indexed_chunk_count == 3
    assert {result.chunk_key for result in results} == {
        "1:0",
        "1:1",
        "2:0",
    }


def test_reject_rebuild_when_repository_is_empty() -> None:
    pipeline = _pipeline(InMemoryChunkRepository())

    with pytest.raises(
        FaissIndexNotBuiltError,
        match="재생성할 문서 청크가 없습니다",
    ):
        pipeline.rebuild_index()


def test_reject_search_after_index_invalidation() -> None:
    repository = InMemoryChunkRepository()
    repository.save_all(
        [
            _chunk("1", 0, "예금은 금리를 제공한다."),
        ]
    )
    pipeline = _pipeline(repository)
    pipeline.rebuild_index()

    pipeline.invalidate_index()

    with pytest.raises(
        FaissIndexNotBuiltError,
        match="rebuild_index",
    ):
        pipeline.search("예금")


def test_rebuild_drops_replaced_document_chunks() -> None:
    repository = InMemoryChunkRepository()
    repository.save_all(
        [
            _chunk("1", 0, "교체 전 예금 설명"),
            _chunk("1", 1, "삭제될 예금 청크"),
            _chunk("2", 0, "유지할 채권 청크"),
        ]
    )
    pipeline = _pipeline(repository)
    pipeline.rebuild_index()

    repository.replace_document_chunks(
        document_id="1",
        chunks=[
            _chunk("1", 0, "교체 후 예금 설명"),
        ],
    )
    pipeline.invalidate_index()
    indexed_chunk_count = pipeline.rebuild_index()
    results = pipeline.search("교체 후 예금 설명")
    result_keys = {result.chunk_key for result in results}

    assert indexed_chunk_count == 2
    assert result_keys == {
        "1:0",
        "2:0",
    }
    assert "1:1" not in result_keys
