from app.application.chunkers.paragraph import ParagraphChunker
from app.domain.document import SourceDocument


def test_chunk_document_by_paragraphs() -> None:
    document = SourceDocument(
        title="예금 기초",
        content="첫 번째 문단.\n\n두 번째 문단.\n   \n세 번째 문단.\n\n",
        source="deposit.txt",
    )

    chunks = ParagraphChunker().chunk(document)

    assert [chunk.sequence for chunk in chunks] == [0, 1, 2]
    assert [chunk.content for chunk in chunks] == [
        "첫 번째 문단.",
        "두 번째 문단.",
        "세 번째 문단.",
    ]
    assert all(chunk.title == document.title for chunk in chunks)
    assert all(chunk.source == document.source for chunk in chunks)


def test_preserve_single_line_break_inside_paragraph() -> None:
    document = SourceDocument(
        title="예금 기초",
        content="첫 번째 줄.\n같은 문단의 두 번째 줄.",
        source="deposit.txt",
    )

    chunks = ParagraphChunker().chunk(document)

    assert len(chunks) == 1
    assert chunks[0].content == "첫 번째 줄.\n같은 문단의 두 번째 줄."


def test_ignore_empty_content() -> None:
    document = SourceDocument(
        title="빈 문서",
        content="  \n\n\t\n  ",
        source="empty.txt",
    )

    chunks = ParagraphChunker().chunk(document)

    assert chunks == []
