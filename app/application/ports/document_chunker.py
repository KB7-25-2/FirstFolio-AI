from typing import Protocol

from app.domain.chunk import DocumentChunk
from app.domain.document import SourceDocument


class DocumentChunker(Protocol):
    def chunk(self, document: SourceDocument) -> list[DocumentChunk]: ...
