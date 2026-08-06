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
