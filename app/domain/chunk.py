from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    sequence: int
    content: str
    title: str
    source: str
