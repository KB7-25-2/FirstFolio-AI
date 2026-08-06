from app.application.chunkers.news import NewsChunker
from app.application.chunkers.paragraph import ParagraphChunker
from app.domain.document import SourceDocument


def test_news_chunker_keeps_paragraph_fallback_until_news_rules_are_added() -> None:
    document = SourceDocument(
        document_id="news-001",
        title="News",
        content="First paragraph.\n\nSecond paragraph.",
        source="news.txt",
    )
    paragraph_chunker = ParagraphChunker()

    chunks = NewsChunker(paragraph_chunker).chunk(document)

    assert chunks == paragraph_chunker.chunk(document)
