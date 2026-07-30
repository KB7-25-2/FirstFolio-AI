from dataclasses import dataclass

from app.domain.chunk import DocumentChunk


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk: DocumentChunk
    score: float
