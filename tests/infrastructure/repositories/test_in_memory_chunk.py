from app.domain.chunk import DocumentChunk
from app.infrastructure.repositories.in_memory_chunk import (
    InMemoryChunkRepository,
)


def create_chunk(
    sequence: int,
    content: str,
) -> DocumentChunk:
    return DocumentChunk(
        document_id="document-001",
        chunk_key=f"document-001:{sequence}",
        sequence=sequence,
        content=content,
        title="금융 기초",
        source="financial_guide.txt",
    )


def test_save_and_find_all_chunks() -> None:
    repository = InMemoryChunkRepository()
    chunks = [
        create_chunk(0, "첫 번째 청크"),
        create_chunk(1, "두 번째 청크"),
    ]

    repository.save_all(chunks)

    assert repository.find_all() == chunks


def test_replace_chunk_with_same_chunk_key() -> None:
    repository = InMemoryChunkRepository()
    original_chunk = create_chunk(0, "기존 내용")
    updated_chunk = create_chunk(0, "수정된 내용")

    repository.save_all([original_chunk])
    repository.save_all([updated_chunk])

    assert repository.find_all() == [updated_chunk]


def test_find_chunks_in_requested_key_order() -> None:
    repository = InMemoryChunkRepository()
    first_chunk = create_chunk(0, "첫 번째 청크")
    second_chunk = create_chunk(1, "두 번째 청크")
    repository.save_all([first_chunk, second_chunk])

    chunks = repository.find_by_chunk_keys(
        [
            "document-001:1",
            "missing-key",
            "document-001:0",
        ]
    )

    assert chunks == [second_chunk, first_chunk]
