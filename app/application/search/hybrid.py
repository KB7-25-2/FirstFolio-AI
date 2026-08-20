from app.application.ports.chunk_repository import ChunkRepository
from app.core.config import Settings
from app.domain.search import SearchResult
from app.infrastructure.search.bm25 import BM25Search
from app.infrastructure.search.faiss import FaissVectorSearch


class HybridSearch:
    def __init__(
        self,
        settings: Settings,
        bm25_search: BM25Search,
        faiss_search: FaissVectorSearch,
        chunk_repository: ChunkRepository,
    ) -> None:
        self._settings = settings
        self._bm25_search = bm25_search
        self._faiss_search = faiss_search
        self._chunk_repository = chunk_repository

    def search(
        self,
        query: str,
    ) -> list[SearchResult]:
        candidate_top_k = self._settings.search_candidate_top_k
        rrf_k = self._settings.search_rrf_k

        bm25_results = (
            self._bm25_search.search(
                query=query,
                top_k=candidate_top_k,
            )
            if self._settings.bm25_weight > 0
            else []
        )
        faiss_results = (
            self._faiss_search.search(
                query=query,
                top_k=candidate_top_k,
            )
            if self._settings.faiss_weight > 0
            else []
        )

        scores_by_chunk_key: dict[str, float] = {}
        chunks_by_chunk_key = {
            result.chunk.chunk_key: result.chunk for result in bm25_results
        }

        for rank, result in enumerate(
            bm25_results,
            start=1,
        ):
            chunk_key = result.chunk.chunk_key
            rank_score = self._settings.bm25_weight / (rrf_k + rank)

            scores_by_chunk_key[chunk_key] = (
                scores_by_chunk_key.get(chunk_key, 0.0) + rank_score
            )

        faiss_chunk_keys = [result.chunk_key for result in faiss_results]

        if faiss_chunk_keys:
            faiss_chunks = self._chunk_repository.find_by_chunk_keys(faiss_chunk_keys)

            for rank, (result, chunk) in enumerate(
                zip(
                    faiss_results,
                    faiss_chunks,
                    strict=True,
                ),
                start=1,
            ):
                chunks_by_chunk_key[result.chunk_key] = chunk
                rank_score = self._settings.faiss_weight / (rrf_k + rank)

                scores_by_chunk_key[result.chunk_key] = (
                    scores_by_chunk_key.get(result.chunk_key, 0.0) + rank_score
                )

        combined_results = [
            SearchResult(
                chunk=chunks_by_chunk_key[chunk_key],
                score=score,
            )
            for chunk_key, score in scores_by_chunk_key.items()
        ]
        combined_results.sort(
            key=lambda result: (
                -result.score,
                result.chunk.chunk_key,
            )
        )

        return combined_results[: self._settings.search_top_k]
