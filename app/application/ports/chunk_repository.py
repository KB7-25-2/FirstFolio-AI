from collections.abc import Sequence
from typing import Protocol

from app.domain.chunk import DocumentChunk


class ChunkNotFoundError(LookupError):
    pass


class ChunkRepository(Protocol):
    # 청킹 결과 저장
    def save_all(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> None: ...

    # 같은 문서의 기존 청크를 새로운 청크로 교체
    def replace_document_chunks(
        self,
        document_id: str,
        chunks: Sequence[DocumentChunk],
    ) -> None: ...

    # 전체 청크를 불러와 BM25 색인 재구축
    def find_all(self) -> list[DocumentChunk]: ...

    # FAISS가 반환한 키로 MySQL 청크 본문 조회
    def find_by_chunk_keys(
        self,
        chunk_keys: Sequence[str],
    ) -> list[DocumentChunk]: ...
