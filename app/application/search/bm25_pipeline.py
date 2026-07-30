from pathlib import Path

from app.application.chunkers.paragraph import ParagraphChunker
from app.core.config import Settings
from app.domain.search import SearchResult
from app.infrastructure.document_loaders.text import TextDocumentLoader
from app.infrastructure.search.bm25 import BM25Search
from app.infrastructure.tokenizers.kiwi import KiwiTokenizer


class SearchIndexNotBuiltError(RuntimeError):
    pass


# 파이프라인 구성
class BM25SearchPipeline:
    def __init__(self, settings: Settings) -> None:
        self._top_k = settings.search_top_k
        self._loader = TextDocumentLoader()  # 파일 읽기
        self._chunker = ParagraphChunker()  # 문단 분리
        self._tokenizer = KiwiTokenizer()  # 형태소 분석
        self._search_engine: BM25Search | None = None  # 검색 점수 계산

    def build_index(self, path: str | Path) -> int:
        document = self._loader.load(path)
        chunks = self._chunker.chunk(document)

        self._search_engine = BM25Search(
            chunks=chunks,
            tokenizer=self._tokenizer,
        )

        return len(chunks)

    def search(self, query: str) -> list[SearchResult]:
        if self._search_engine is None:
            raise SearchIndexNotBuiltError(
                "BM25 검색 전에 문서 색인을 생성해야 합니다."
            )

        return self._search_engine.search(
            query=query,
            top_k=self._top_k,
        )
