from app.application.chunkers.news import NewsChunker
from app.application.chunkers.paragraph import ParagraphChunker
from app.application.chunkers.registry import create_default_chunker_registry
from app.application.chunkers.textbook import TextbookChunker


def test_default_registry_selects_document_type_chunkers() -> None:
    registry = create_default_chunker_registry()

    assert isinstance(registry.get("textbook"), TextbookChunker)
    assert isinstance(registry.get("news"), NewsChunker)


def test_default_registry_uses_paragraph_chunker_as_fallback() -> None:
    registry = create_default_chunker_registry()

    assert isinstance(registry.get("report"), ParagraphChunker)
