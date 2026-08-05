from app.application.chunkers.paragraph import ParagraphChunker
from app.domain.document import SourceDocument


def test_chunk_document_by_paragraphs() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="예금 기초",
        content="첫 번째 문단.\n\n두 번째 문단.\n   \n세 번째 문단.\n\n",
        source="deposit.txt",
    )

    chunks = ParagraphChunker().chunk(document)

    assert [chunk.sequence for chunk in chunks] == [0, 1, 2]
    assert all(chunk.document_id == "document-001" for chunk in chunks)
    assert [chunk.chunk_key for chunk in chunks] == [
        "document-001:0",
        "document-001:1",
        "document-001:2",
    ]
    assert [chunk.content for chunk in chunks] == [
        "첫 번째 문단.",
        "두 번째 문단.",
        "세 번째 문단.",
    ]
    assert all(chunk.title == document.title for chunk in chunks)
    assert all(chunk.source == document.source for chunk in chunks)
    assert all(chunk.heading is None for chunk in chunks)


def test_preserve_single_line_break_inside_paragraph() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="예금 기초",
        content="첫 번째 줄.\n같은 문단의 두 번째 줄.",
        source="deposit.txt",
    )

    chunks = ParagraphChunker().chunk(document)

    assert len(chunks) == 1
    assert chunks[0].content == "첫 번째 줄.\n같은 문단의 두 번째 줄."


def test_ignore_empty_content() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="빈 문서",
        content="  \n\n\t\n  ",
        source="empty.txt",
    )

    chunks = ParagraphChunker().chunk(document)

    assert chunks == []


def test_extract_and_propagate_numbered_textbook_headings() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="금융 교과서",
        content=(
            "III. 저축과 투자\n"
            "1. 저축과 저축 상품\n"
            "1) 가계의 저축 의사 결정\n"
            "첫 번째 본문.\n\n"
            "제목을 이어받는 본문.\n\n"
            "2. 금융 투자 상품\n"
            "새 단원의 본문.\n\n"
            "IV. 신용과 위험 관리\n"
            "새 대단원의 본문.\n\n"
            "저축 상품의 종류와 특징 가계가 여유 자금을 운용한다."
        ),
        source="financial_textbook.txt",
    )

    chunks = ParagraphChunker().chunk(
        document,
        extract_textbook_headings=True,
    )

    assert [chunk.heading for chunk in chunks] == [
        "가계의 저축 의사 결정",
        "가계의 저축 의사 결정",
        "금융 투자 상품",
        "신용과 위험 관리",
        "신용과 위험 관리",
    ]


def test_textbook_heading_metadata_does_not_change_chunk_structure() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="금융 교과서",
        content=(
            "1) 가계의 저축 의사 결정\n첫 번째 본문.\n\n"
            "두 번째 본문.\n\n"
            "2) 가계의 저축 상품 선택\n세 번째 본문."
        ),
        source="financial_textbook.txt",
    )

    default_chunks = ParagraphChunker().chunk(document)
    heading_chunks = ParagraphChunker().chunk(
        document,
        extract_textbook_headings=True,
    )

    assert len(heading_chunks) == len(default_chunks)
    assert [chunk.content for chunk in heading_chunks] == [
        chunk.content for chunk in default_chunks
    ]
    assert [chunk.sequence for chunk in heading_chunks] == [
        chunk.sequence for chunk in default_chunks
    ]
    assert [chunk.chunk_key for chunk in heading_chunks] == [
        chunk.chunk_key for chunk in default_chunks
    ]
    assert all(chunk.heading is None for chunk in default_chunks)


def test_leave_heading_empty_when_textbook_has_no_numbered_heading() -> None:
    document = SourceDocument(
        document_id="document-001",
        title="금융 교과서",
        content=(
            "저축 상품의 종류와 특징\n첫 번째 본문.\n\n"
            "저축 상품의 종류와 특징 두 번째 본문."
        ),
        source="financial_textbook.txt",
    )

    chunks = ParagraphChunker().chunk(
        document,
        extract_textbook_headings=True,
    )

    assert all(chunk.heading is None for chunk in chunks)
