from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IndexHealthCheck:
    corpus_chunk_count: int
    faiss_vector_count: int

    @property
    def matches(self) -> bool:
        return self.corpus_chunk_count == self.faiss_vector_count


class SearchIndexMismatchError(RuntimeError):
    pass


def check_index_matches_corpus(
    *,
    corpus_chunk_count: int,
    faiss_vector_count: int,
) -> IndexHealthCheck:
    return IndexHealthCheck(
        corpus_chunk_count=corpus_chunk_count,
        faiss_vector_count=faiss_vector_count,
    )


def ensure_index_matches_corpus(
    *,
    corpus_chunk_count: int,
    faiss_vector_count: int,
) -> None:
    """검색 품질 측정처럼 정확한 일치가 필요한 곳에서만 사용한다.

    운영 서비스 기동 경로(quiz_mvp.create_quiz_generation_service)는 이
    함수 대신 check_index_matches_corpus로 경고만 남기고 계속 진행한다.
    """
    check = check_index_matches_corpus(
        corpus_chunk_count=corpus_chunk_count,
        faiss_vector_count=faiss_vector_count,
    )

    if not check.matches:
        raise SearchIndexMismatchError(
            "FAISS 인덱스 벡터 수와 MySQL 청크 수가 일치하지 않습니다: "
            f"corpus={check.corpus_chunk_count}, faiss={check.faiss_vector_count}. "
            "FAISS 재색인이 필요합니다."
        )
