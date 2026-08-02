from pathlib import Path

from app.application.chunkers.paragraph import ParagraphChunker
from app.application.ports.chunk_repository import ChunkRepository
from app.core.config import Settings
from app.domain.search import SearchResult
from app.infrastructure.document_loaders.text import TextDocumentLoader
from app.infrastructure.search.bm25 import BM25Search
from app.infrastructure.tokenizers.kiwi import KiwiTokenizer


class SearchIndexNotBuiltError(RuntimeError):
    pass


class BM25SearchPipeline:
    def __init__(
        self,
        settings: Settings,
        chunk_repository: ChunkRepository,
    ) -> None:
        self._top_k = settings.search_top_k
        self._chunk_repository = chunk_repository
        self._loader = TextDocumentLoader()
        self._chunker = ParagraphChunker()
        self._tokenizer = KiwiTokenizer()
        self._search_engine: BM25Search | None = None

    def register_document(
        self,
        path: str | Path,
        document_id: str,
    ) -> int:
        document = self._loader.load(
            path,
            document_id=document_id,
        )
        chunks = self._chunker.chunk(document)

        self._chunk_repository.replace_document_chunks(
            document_id=document_id,
            chunks=chunks,
        )

        self.invalidate_index()

        return len(chunks)

    def invalidate_index(self) -> None:
        self._search_engine = None

    def rebuild_index(self) -> int:
        stored_chunks = self._chunk_repository.find_all()

        if not stored_chunks:
            raise SearchIndexNotBuiltError(
                "BM25 검색 인덱스를 재생성할 문서 청크가 없습니다."
            )

        self._search_engine = BM25Search(
            chunks=stored_chunks,
            tokenizer=self._tokenizer,
        )

        return len(stored_chunks)

    def search(self, query: str) -> list[SearchResult]:
        if self._search_engine is None:
            raise SearchIndexNotBuiltError(
                "BM25 검색 인덱스가 없거나 문서 변경 후 재생성이 필요합니다.\n"
                "rebuild_index()를 먼저 실행해 주세요."
            )

        return self._search_engine.search(
            query=query,
            top_k=self._top_k,
        )
