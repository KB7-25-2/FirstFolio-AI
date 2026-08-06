import pytest

from app.application.chunkers.news import (
    InvalidNewsDocumentError,
    NewsChunker,
)
from app.application.chunkers.paragraph import ParagraphChunker
from app.domain.document import SourceDocument

HEADER_VALUES = (
    ("\ubb38\uc11c\uc720\ud615", "\ub274\uc2a4"),
    ("\uc81c\ubaa9", "Rates rise 12.5% on 2026-08-05"),
    ("\uc5b8\ub860\uc0ac", "First Finance"),
    ("\uce74\ud14c\uace0\ub9ac", "Finance > Banking"),
    ("\uc791\uc131\uc790", "Reporter Kim"),
    ("\ubc1c\ud589\uc77c", "2026-08-05 10:57"),
    ("\uae30\uc900\uc2dc\uc810", "2026-07-31"),
    ("\uc218\uc9d1\uc77c", "2026-08-06"),
    ("\uae30\uc0ac ID", "article-001"),
    ("\uc6d0\ubb38 URL", "https://example.com/news/article-001"),
    ("\ubcf8\ubb38 \ud615\ud0dc", "Original-based summary"),
)
CORE_SECTION = "\ud575\uc2ec \ub0b4\uc6a9"
KEYWORD_SECTION = "\ud0a4\uc6cc\ub4dc"
NOTICE_SECTION = "\ucd9c\ucc98 \uc720\uc758\uc0ac\ud56d"


def _content(
    *,
    header_values: tuple[tuple[str, str], ...] = HEADER_VALUES,
    core_paragraphs: tuple[str, ...] = ("Core paragraph one.", "Core paragraph two."),
    keywords: str = "rates, deposits, banks",
    notice: str = "Check the original source for details.",
) -> str:
    header = "\n".join(f"{label}: {value}" for label, value in header_values)
    paragraphs = (
        header,
        CORE_SECTION,
        *core_paragraphs,
        KEYWORD_SECTION,
        keywords,
        NOTICE_SECTION,
        notice,
    )
    return "\n\n".join(paragraphs)


def _document(content: str, document_id: str = "news-001") -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        title="Registered news title",
        content=content,
        source="news.txt",
    )


def test_short_news_stays_in_one_chunk_with_exact_metadata() -> None:
    content = _content()

    chunks = NewsChunker(ParagraphChunker()).chunk(_document(content))

    assert len(chunks) == 1
    assert chunks[0].content == content
    assert chunks[0].sequence == 0
    assert chunks[0].chunk_key == "news-001:0"
    assert chunks[0].heading is None
    assert chunks[0].metadata == {
        "document_type": "\ub274\uc2a4",
        "title": "Rates rise 12.5% on 2026-08-05",
        "publisher": "First Finance",
        "category": "Finance > Banking",
        "author": "Reporter Kim",
        "published_at": "2026-08-05 10:57",
        "reference_at": "2026-07-31",
        "collected_at": "2026-08-06",
        "article_id": "article-001",
        "source_url": "https://example.com/news/article-001",
        "body_type": "Original-based summary",
    }


@pytest.mark.parametrize("invalid_index", [0, 4, 10])
def test_rejects_missing_news_header_field(invalid_index: int) -> None:
    header_values = HEADER_VALUES[:invalid_index] + HEADER_VALUES[invalid_index + 1 :]

    with pytest.raises(InvalidNewsDocumentError, match="header"):
        NewsChunker(ParagraphChunker()).chunk(
            _document(_content(header_values=header_values))
        )


def test_rejects_out_of_order_news_header_fields() -> None:
    header_values = list(HEADER_VALUES)
    header_values[1], header_values[2] = header_values[2], header_values[1]

    with pytest.raises(InvalidNewsDocumentError, match="header"):
        NewsChunker(ParagraphChunker()).chunk(
            _document(_content(header_values=tuple(header_values)))
        )


@pytest.mark.parametrize(
    "content",
    [
        _content().replace(f"\n\n{KEYWORD_SECTION}\n\n", "\n\n"),
        _content().replace(
            f"\n\n{KEYWORD_SECTION}\n\nrates, deposits, banks\n\n{NOTICE_SECTION}\n\n",
            f"\n\n{NOTICE_SECTION}\n\nCheck first.\n\n{KEYWORD_SECTION}\n\n",
        ),
    ],
)
def test_rejects_missing_or_out_of_order_news_sections(content: str) -> None:
    with pytest.raises(InvalidNewsDocumentError, match="section"):
        NewsChunker(ParagraphChunker()).chunk(_document(content))


def test_long_news_splits_on_paragraphs_without_crossing_sections() -> None:
    content = _content(
        core_paragraphs=("A" * 200, "B" * 200, "C" * 200),
        keywords="K" * 300,
        notice="N" * 300,
    )

    chunks = NewsChunker(ParagraphChunker(), max_chars=450).chunk(_document(content))

    assert len(chunks) > 3
    assert "\n\n".join(chunk.content for chunk in chunks) == content
    assert [chunk.sequence for chunk in chunks] == list(range(len(chunks)))
    assert [chunk.chunk_key for chunk in chunks] == [
        f"news-001:{sequence}" for sequence in range(len(chunks))
    ]
    assert {chunk.heading for chunk in chunks} == {
        CORE_SECTION,
        KEYWORD_SECTION,
        NOTICE_SECTION,
    }
    assert all(chunk.metadata is not None for chunk in chunks)
    assert all(chunk.metadata["article_id"] == "article-001" for chunk in chunks)
    assert all(chunk.metadata["section"] == chunk.heading for chunk in chunks)
    assert all(
        sum(
            section in chunk.content
            for section in (CORE_SECTION, KEYWORD_SECTION, NOTICE_SECTION)
        )
        <= 1
        for chunk in chunks
    )

    first_core = next(chunk for chunk in chunks if chunk.heading == CORE_SECTION)
    first_keyword = next(chunk for chunk in chunks if chunk.heading == KEYWORD_SECTION)
    first_notice = next(chunk for chunk in chunks if chunk.heading == NOTICE_SECTION)
    assert f"{CORE_SECTION}\n\n{'A' * 200}" in first_core.content
    assert first_keyword.content == f"{KEYWORD_SECTION}\n\n{'K' * 300}"
    assert first_notice.content == f"{NOTICE_SECTION}\n\n{'N' * 300}"


def test_keeps_single_oversized_paragraph_intact() -> None:
    oversized = "X" * 600
    content = _content(core_paragraphs=(oversized, "final core paragraph"))

    chunks = NewsChunker(ParagraphChunker(), max_chars=350).chunk(_document(content))

    assert oversized in [
        paragraph for chunk in chunks for paragraph in chunk.content.split("\n\n")
    ]
    assert "\n\n".join(chunk.content for chunk in chunks) == content


def test_separate_news_documents_never_share_content_or_identifiers() -> None:
    second_headers = tuple(
        (label, "article-002" if label == "\uae30\uc0ac ID" else value)
        for label, value in HEADER_VALUES
    )
    first_chunks = NewsChunker(ParagraphChunker()).chunk(_document(_content()))
    second_chunks = NewsChunker(ParagraphChunker()).chunk(
        _document(
            _content(
                header_values=second_headers,
                core_paragraphs=("Only second article content.",),
            ),
            document_id="news-002",
        )
    )

    assert first_chunks[0].metadata["article_id"] == "article-001"
    assert second_chunks[0].metadata["article_id"] == "article-002"
    assert first_chunks[0].chunk_key == "news-001:0"
    assert second_chunks[0].chunk_key == "news-002:0"
    assert "Only second article content." not in first_chunks[0].content


def test_rejects_non_positive_max_chars() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        NewsChunker(ParagraphChunker(), max_chars=0)
