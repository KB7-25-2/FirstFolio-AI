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
            "Preface paragraph long enough to remain standalone without any "
            "heading label at all.\n\n"
            f"{_chapter(3, 'Savings')}\n\n"
            "3.1 Income\n\n"
            "Section introduction paragraph with sufficient length to end "
            "this merged group properly.\n\n"
            "1) Earned income\n\n"
            "Subsection body paragraph that is long enough to stand as the "
            "end of its own merged group.\n\n"
            "3.2 Expenses\n\n"
            "Next section body paragraph with enough characters to close "
            "out this particular group nicely.\n\n"
            f"{_chapter(4, 'Investment')}\n\n"
            "Next chapter body paragraph that has plenty of length to "
            "finish the final merged group here."
        ),
        source="financial_textbook.txt",
    )

    chunks = TextbookChunker(ParagraphChunker()).chunk(document)

    # 제목·목차 줄(짧고 문장으로 끝나지 않음)은 뒤따르는 본문 문단에 합쳐진다.
    # 각 문단은 충분히 길고 마침표로 끝나므로 그 지점에서 병합이 멈춘다.
    assert [chunk.heading for chunk in chunks] == [
        None,
        "Income",
        "Earned income",
        "Expenses",
        "Investment",
    ]
    assert [chunk.metadata for chunk in chunks] == [
        None,
        {"chapter_heading": "Savings", "section_heading": "Income"},
        {
            "chapter_heading": "Savings",
            "section_heading": "Income",
            "subsection_heading": "Earned income",
        },
        {"chapter_heading": "Savings", "section_heading": "Expenses"},
        {"chapter_heading": "Investment"},
    ]
    assert chunks[1].content == (
        f"{_chapter(3, 'Savings')}\n\n"
        "3.1 Income\n\n"
        "Section introduction paragraph with sufficient length to end "
        "this merged group properly."
    )
    assert [chunk.chunk_key for chunk in chunks] == [
        f"document-001:{sequence}" for sequence in range(len(chunks))
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


def test_keeps_long_sentence_ending_paragraphs_as_separate_chunks() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="Financial Textbook",
        content=(
            "Introductory paragraph with enough length to remain a real "
            "standalone paragraph.\n\n"
            "Second standalone paragraph that is long enough to avoid any "
            "merge with its neighbor."
        ),
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


def test_merges_short_heading_only_paragraph_into_following_chunk() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="Financial Textbook",
        content=(
            f"{_chapter(3, 'Savings')}\n\n"
            "A sufficiently long section paragraph that will not be "
            "merged away because it ends properly."
        ),
        source="financial_textbook.txt",
    )

    chunks = TextbookChunker(ParagraphChunker()).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].chunk_key == "document-001:0"
    assert chunks[0].heading == "Savings"
    assert chunks[0].metadata == {"chapter_heading": "Savings"}
    assert chunks[0].content == (
        f"{_chapter(3, 'Savings')}\n\n"
        "A sufficiently long section paragraph that will not be "
        "merged away because it ends properly."
    )


def test_merges_trailing_short_chunk_into_previous_chunk() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="Financial Textbook",
        content=(
            "A sufficiently long opening paragraph that stands on its own "
            "without needing anything else.\n\n"
            "Short trailing note"
        ),
        source="financial_textbook.txt",
    )

    chunks = TextbookChunker(ParagraphChunker()).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].chunk_key == "document-001:0"
    assert chunks[0].heading is None
    assert chunks[0].content == (
        "A sufficiently long opening paragraph that stands on its own "
        "without needing anything else.\n\n"
        "Short trailing note"
    )
