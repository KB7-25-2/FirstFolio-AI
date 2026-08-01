from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    document_id: str
    chunk_key: str
    sequence: int
    content: str
    title: str
    source: str
