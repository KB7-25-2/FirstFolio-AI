from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceDocument:
    document_id: str
    title: str
    content: str
    source: str
