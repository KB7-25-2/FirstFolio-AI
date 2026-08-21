from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    document_id: str
    chunk_key: str
    sequence: int
    content: str
    title: str
    source: str
    heading: str | None = None
    metadata: dict[str, str] | None = None
    source_url: str | None = None
    published_at: datetime | None = None

    def searchable_text(self) -> str:
        """색인용 텍스트. 인용·근거 검증에는 content를 그대로 써야 하므로,
        이 값은 BM25 토큰화·FAISS 임베딩 입력에만 사용한다."""
        if self.heading:
            return f"{self.heading}\n{self.content}"
        return self.content
