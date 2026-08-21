from app.domain.chunk import DocumentChunk


def create_chunk(
    *,
    content: str,
    heading: str | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        document_id="doc",
        chunk_key="doc:0",
        sequence=0,
        content=content,
        title="제목",
        source="doc.txt",
        heading=heading,
    )


def test_searchable_text_returns_content_when_no_heading() -> None:
    chunk = create_chunk(content="예금은 금융기관에 돈을 맡기는 상품이다.")

    assert chunk.searchable_text() == "예금은 금융기관에 돈을 맡기는 상품이다."


def test_searchable_text_prefixes_heading_before_content() -> None:
    chunk = create_chunk(
        content="예금은 금융기관에 돈을 맡기는 상품이다.",
        heading="예금의 정의",
    )

    assert (
        chunk.searchable_text()
        == "예금의 정의\n예금은 금융기관에 돈을 맡기는 상품이다."
    )
