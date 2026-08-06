from collections.abc import Mapping

from app.application.chunkers.news import NewsChunker
from app.application.chunkers.paragraph import ParagraphChunker
from app.application.chunkers.textbook import TextbookChunker
from app.application.ports.document_chunker import DocumentChunker


class DocumentChunkerRegistry:
    def __init__(
        self,
        chunkers: Mapping[str, DocumentChunker],
        fallback_chunker: DocumentChunker,
    ) -> None:
        self._chunkers = dict(chunkers)
        self._fallback_chunker = fallback_chunker

    def get(self, document_type: str) -> DocumentChunker:
        return self._chunkers.get(document_type, self._fallback_chunker)


def create_default_chunker_registry() -> DocumentChunkerRegistry:
    paragraph_chunker = ParagraphChunker()

    return DocumentChunkerRegistry(
        chunkers={
            "textbook": TextbookChunker(paragraph_chunker),
            "news": NewsChunker(paragraph_chunker),
        },
        fallback_chunker=paragraph_chunker,
    )
