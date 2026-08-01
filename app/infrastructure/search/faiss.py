import json
from collections.abc import Sequence
from pathlib import Path
from typing import Self

import faiss
import numpy as np

from app.application.ports.embedding import EmbeddingClient
from app.domain.chunk import DocumentChunk
from app.domain.search import VectorSearchResult


class FaissVectorSearch:
    def __init__(
        self,
        chunks: Sequence[DocumentChunk],
        embedding_client: EmbeddingClient,
    ) -> None:
        if not chunks:
            raise ValueError("FAISS 색인을 생성할 문서 청크가 없습니다.")

        embeddings = embedding_client.embed_documents(
            [chunk.content for chunk in chunks]
        )

        if len(embeddings) != len(chunks):
            raise ValueError("문서 청크 수와 임베딩 벡터 수가 일치하지 않습니다.")

        vectors = self._prepare_vectors(embeddings)

        self._embedding_client = embedding_client
        self._chunk_keys = [chunk.chunk_key for chunk in chunks]
        self._index = faiss.IndexFlatIP(vectors.shape[1])
        self._index.add(vectors)

    def save(
        self,
        index_path: str | Path,
        mapping_path: str | Path,
    ) -> None:
        index_file = Path(index_path)
        mapping_file = Path(mapping_path)

        index_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        mapping_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        faiss.write_index(
            self._index,
            str(index_file),
        )

        mapping_data = {
            "chunk_keys": self._chunk_keys,
        }
        mapping_file.write_text(
            json.dumps(
                mapping_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(
        cls,
        index_path: str | Path,
        mapping_path: str | Path,
        embedding_client: EmbeddingClient,
    ) -> Self:
        index_file = Path(index_path)
        mapping_file = Path(mapping_path)

        if not index_file.is_file():
            raise FileNotFoundError(
                f"FAISS 인덱스 파일을 찾을 수 없습니다: {index_file}"
            )

        if not mapping_file.is_file():
            raise FileNotFoundError(
                f"FAISS 청크 키 매핑 파일을 찾을 수 없습니다: {mapping_file}"
            )

        index = faiss.read_index(str(index_file))

        try:
            mapping_data = json.loads(mapping_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                "FAISS 청크 키 매핑 파일이 올바른 JSON 형식이 아닙니다."
            ) from error

        if not isinstance(mapping_data, dict):
            raise ValueError("FAISS 청크 키 매핑 데이터는 객체 형식이어야 합니다.")

        chunk_keys = mapping_data.get("chunk_keys")

        if not isinstance(chunk_keys, list) or not all(
            isinstance(chunk_key, str) for chunk_key in chunk_keys
        ):
            raise ValueError("FAISS 청크 키 매핑 데이터가 올바르지 않습니다.")

        if not chunk_keys:
            raise ValueError("FAISS 청크 키 매핑에 저장된 식별자가 없습니다.")

        if index.ntotal != len(chunk_keys):
            raise ValueError("FAISS 인덱스의 벡터 수와 청크 키 수가 일치하지 않습니다.")

        instance = cls.__new__(cls)
        instance._embedding_client = embedding_client
        instance._chunk_keys = chunk_keys
        instance._index = index

        return instance

    def search(
        self,
        query: str,
        top_k: int,
    ) -> list[VectorSearchResult]:
        if top_k < 1:
            raise ValueError("상위 검색 결과 개수는 1 이상이어야 합니다.")

        if not query.strip():
            return []

        query_embedding = self._embedding_client.embed_query(query)
        query_vector = self._prepare_vectors([query_embedding])

        if query_vector.shape[1] != self._index.d:
            raise ValueError(
                "검색어 임베딩과 FAISS 인덱스의 벡터 차원이 일치하지 않습니다."
            )

        result_count = min(
            top_k,
            len(self._chunk_keys),
        )
        scores, positions = self._index.search(
            query_vector,
            result_count,
        )

        return [
            VectorSearchResult(
                chunk_key=self._chunk_keys[int(position)],
                score=float(score),
            )
            for score, position in zip(
                scores[0],
                positions[0],
                strict=True,
            )
            if position >= 0
        ]

    @staticmethod
    def _prepare_vectors(
        embeddings: list[list[float]],
    ) -> np.ndarray:
        if not embeddings:
            raise ValueError("FAISS 색인에 사용할 임베딩 벡터가 없습니다.")

        vector_dimension = len(embeddings[0])

        if vector_dimension < 1:
            raise ValueError("임베딩 벡터 차원은 1 이상이어야 합니다.")

        if any(len(embedding) != vector_dimension for embedding in embeddings):
            raise ValueError("모든 임베딩 벡터의 차원이 같아야 합니다.")

        vectors = np.asarray(
            embeddings,
            dtype=np.float32,
        )

        vector_norms = np.linalg.norm(
            vectors,
            axis=1,
        )

        if np.any(vector_norms == 0):
            raise ValueError("크기가 0인 임베딩 벡터는 색인할 수 없습니다.")

        faiss.normalize_L2(vectors)

        return vectors
