from collections.abc import Sequence

from rank_bm25 import BM25Okapi

from app.domain.chunk import DocumentChunk
from app.domain.search import SearchResult
from app.infrastructure.tokenizers.kiwi import KiwiTokenizer


class BM25Search:
    def __init__(
        self,
        chunks: Sequence[DocumentChunk],
        tokenizer: KiwiTokenizer,
    ) -> None:
        if not chunks:
            raise ValueError("BM25 색인을 생성할 문서 청크가 없습니다.")

        self._chunks = list(chunks)
        self._tokenizer = tokenizer

        tokenized_chunks = [
            self._tokenizer.tokenize(chunk.searchable_text()) for chunk in self._chunks
        ]

        if not any(tokenized_chunks):
            raise ValueError("BM25 색인에 사용할 검색 토큰이 없습니다.")

        self._index = BM25Okapi(tokenized_chunks)

    def search(
        self,
        query: str,
        top_k: int,
    ) -> list[SearchResult]:
        if top_k < 1:
            raise ValueError("상위 검색 결과 개수는 1 이상이어야 합니다.")

        query_tokens = self._tokenizer.tokenize(query)

        if not query_tokens:
            return []

        scores = self._index.get_scores(query_tokens)
        results: list[SearchResult] = []

        for chunk, score in zip(self._chunks, scores, strict=True):
            score_value = float(score)

            if score_value > 0:
                results.append(
                    SearchResult(
                        chunk=chunk,
                        score=score_value,
                    )
                )

        results.sort(
            key=lambda result: result.score,
            reverse=True,
        )

        return results[:top_k]
