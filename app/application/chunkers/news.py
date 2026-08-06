from app.application.ports.document_chunker import DocumentChunker
from app.domain.chunk import DocumentChunk
from app.domain.document import SourceDocument


class NewsChunker:
    def __init__(self, paragraph_chunker: DocumentChunker) -> None:
        self._paragraph_chunker = paragraph_chunker

    def chunk(self, document: SourceDocument) -> list[DocumentChunk]:
        return self._paragraph_chunker.chunk(document)
