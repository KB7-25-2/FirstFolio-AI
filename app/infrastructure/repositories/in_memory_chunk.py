from collections.abc import Sequence

from app.domain.chunk import DocumentChunk


class InMemoryChunkRepository:
    def __init__(self) -> None:
        self._chunks_by_key: dict[str, DocumentChunk] = {}

    def save_all(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> None:
        for chunk in chunks:
            self._chunks_by_key[chunk.chunk_key] = chunk

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: Sequence[DocumentChunk],
    ) -> None:
        existing_chunk_keys = [
            chunk_key
            for chunk_key, chunk in self._chunks_by_key.items()
            if chunk.document_id == document_id
        ]

        for chunk_key in existing_chunk_keys:
            del self._chunks_by_key[chunk_key]

        self.save_all(chunks)

    def find_all(self) -> list[DocumentChunk]:
        return sorted(
            self._chunks_by_key.values(),
            key=lambda chunk: (chunk.document_id, chunk.sequence),
        )

    def find_by_chunk_keys(
        self,
        chunk_keys: Sequence[str],
    ) -> list[DocumentChunk]:
        return [
            self._chunks_by_key[chunk_key]
            for chunk_key in chunk_keys
            if chunk_key in self._chunks_by_key
        ]
