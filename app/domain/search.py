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


@dataclass(frozen=True, slots=True)
class SearchEvaluationMetrics:
    top_k: int
    evaluated_case_count: int
    recall_at_k: float
    mean_reciprocal_rank: float
