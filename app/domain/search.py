from dataclasses import dataclass

from app.domain.chunk import DocumentChunk


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk: DocumentChunk
    score: float


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    chunk_key: str
    score: float


@dataclass(frozen=True, slots=True)
class SearchEvaluationCase:
    query: str
    relevant_chunk_keys: tuple[str, ...]
    # 재청킹으로 chunk_key가 바뀌어도 정답 청크를 문장으로 다시 찾을 수 있게
    # 보관하는 참고용 필드다. 평가 계산에는 사용하지 않는다.
    relevant_text: str | None = None


@dataclass(frozen=True, slots=True)
class SearchEvaluationMetrics:
    top_k: int
    evaluated_case_count: int
    recall_at_k: float
    mean_reciprocal_rank: float


@dataclass(frozen=True, slots=True)
class EvidenceQualityMetrics:
    topic: str
    retrieved_count: int
    usable_evidence_count: int
    distinct_evidence_count: int
    heading_fragment_count: int
