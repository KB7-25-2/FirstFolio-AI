from app.application.chunkers.paragraph import ParagraphChunker
from app.application.chunkers.textbook import TextbookChunker
from app.domain.document import SourceDocument


def _chapter(number: int, title: str) -> str:
    return f"{chr(0xC81C)}{number}{chr(0xC7A5)} {title}"


def test_extract_and_propagate_textbook_heading_hierarchy() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="Financial Textbook",
        content=(
            "Preface.\n\n"
            f"{_chapter(3, 'Savings')}\n\n"
            "3.1 Income\n\n"
            "Section introduction.\n\n"
            "1) Earned income\n\n"
            "Subsection body.\n\n"
            "3.2 Expenses\n\n"
            "Next section body.\n\n"
            f"{_chapter(4, 'Investment')}\n\n"
            "Next chapter body."
        ),
        source="financial_textbook.txt",
    )

    chunks = TextbookChunker(ParagraphChunker()).chunk(document)

    assert [chunk.heading for chunk in chunks] == [
        None,
        "Savings",
        "Income",
        "Income",
        "Earned income",
        "Earned income",
        "Expenses",
        "Expenses",
        "Investment",
        "Investment",
    ]
    assert [chunk.metadata for chunk in chunks] == [
        None,
        {"chapter_heading": "Savings"},
        {"chapter_heading": "Savings", "section_heading": "Income"},
        {"chapter_heading": "Savings", "section_heading": "Income"},
        {
            "chapter_heading": "Savings",
            "section_heading": "Income",
            "subsection_heading": "Earned income",
        },
        {
            "chapter_heading": "Savings",
            "section_heading": "Income",
            "subsection_heading": "Earned income",
        },
        {"chapter_heading": "Savings", "section_heading": "Expenses"},
        {"chapter_heading": "Savings", "section_heading": "Expenses"},
        {"chapter_heading": "Investment"},
        {"chapter_heading": "Investment"},
    ]


def test_preserve_legacy_numbered_hierarchy_in_one_paragraph() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="Financial Textbook",
        content=(
            "III. Savings and investment\n"
            "1. Savings products\n"
            "1) Deposit decisions\n"
            "Body."
        ),
        source="financial_textbook.txt",
    )

    chunks = TextbookChunker(ParagraphChunker()).chunk(document)

    assert chunks[0].heading == "Deposit decisions"
    assert chunks[0].metadata == {
        "chapter_heading": "Savings and investment",
        "section_heading": "Savings products",
        "subsection_heading": "Deposit decisions",
    }


def test_ignore_ambiguous_and_unnumbered_textbook_headings() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="Financial Textbook",
        content=(
            "1 Heading without a delimiter\n\n"
            f"{chr(0x2460)} Heading or combined body\n\n"
            "Unnumbered heading\n\n"
            "Unnumbered heading Body on the same line."
        ),
        source="financial_textbook.txt",
    )

    chunks = TextbookChunker(ParagraphChunker()).chunk(document)

    assert all(chunk.heading is None for chunk in chunks)
    assert all(chunk.metadata is None for chunk in chunks)


def test_textbook_hierarchy_does_not_change_paragraph_identity() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="Financial Textbook",
        content=f"{_chapter(3, 'Savings')}\n\n3.1 Income\n\nBody.",
        source="financial_textbook.txt",
    )
    paragraph_chunks = ParagraphChunker().chunk(document)

    textbook_chunks = TextbookChunker(ParagraphChunker()).chunk(document)

    assert [chunk.content for chunk in textbook_chunks] == [
        chunk.content for chunk in paragraph_chunks
    ]
    assert [chunk.sequence for chunk in textbook_chunks] == [
        chunk.sequence for chunk in paragraph_chunks
    ]
    assert [chunk.chunk_key for chunk in textbook_chunks] == [
        chunk.chunk_key for chunk in paragraph_chunks
    ]
