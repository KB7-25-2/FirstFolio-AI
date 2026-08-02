from app.application.ports.chunk_repository import ChunkRepository
from app.application.ports.embedding import EmbeddingClient
from app.core.config import Settings
from app.domain.search import VectorSearchResult
from app.infrastructure.search.faiss import FaissVectorSearch


class FaissIndexNotBuiltError(RuntimeError):
    pass


class FaissSearchPipeline:
    def __init__(
        self,
        settings: Settings,
        chunk_repository: ChunkRepository,
        embedding_client: EmbeddingClient,
    ) -> None:
        self._top_k = settings.search_top_k
        self._chunk_repository = chunk_repository
        self._embedding_client = embedding_client
        self._search_engine: FaissVectorSearch | None = None

    def invalidate_index(self) -> None:
        self._search_engine = None

    def rebuild_index(self) -> int:
        stored_chunks = self._chunk_repository.find_all()

        if not stored_chunks:
            raise FaissIndexNotBuiltError(
                "FAISS 검색 인덱스를 재생성할 문서 청크가 없습니다."
            )

        self._search_engine = FaissVectorSearch(
            chunks=stored_chunks,
            embedding_client=self._embedding_client,
        )

        return len(stored_chunks)

    def search(self, query: str) -> list[VectorSearchResult]:
        if self._search_engine is None:
            raise FaissIndexNotBuiltError(
                "FAISS 검색 인덱스가 없거나 문서 변경 후 재생성이 필요합니다.\n"
                "rebuild_index()를 먼저 실행해 주세요."
            )

        return self._search_engine.search(
            query=query,
            top_k=self._top_k,
        )
