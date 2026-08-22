from app.application.chunkers.merge import merge_short_chunks
from app.domain.chunk import DocumentChunk


def create_chunk(
    sequence: int,
    content: str,
    *,
    heading: str | None = None,
    metadata: dict[str, str] | None = None,
    document_id: str = "doc",
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_key=f"{document_id}:{sequence}",
        sequence=sequence,
        content=content,
        title="제목",
        source=f"{document_id}.txt",
        heading=heading,
        metadata=metadata,
    )


def test_return_empty_list_for_no_chunks() -> None:
    assert merge_short_chunks([]) == []


def test_keeps_long_sentence_ending_chunks_untouched() -> None:
    chunks = [
        create_chunk(
            0, "첫 번째 문단은 충분히 길고 마침표로 끝나므로 그대로 유지된다."
        ),
        create_chunk(
            1, "두 번째 문단도 마찬가지로 충분히 길고 마침표로 끝나서 유지된다."
        ),
    ]

    merged = merge_short_chunks(chunks)

    assert [chunk.content for chunk in merged] == [chunk.content for chunk in chunks]
    assert [chunk.chunk_key for chunk in merged] == [
        chunk.chunk_key for chunk in chunks
    ]
    assert [chunk.sequence for chunk in merged] == [0, 1]


def test_merges_short_non_sentence_chunk_into_next_chunk() -> None:
    chunks = [
        create_chunk(0, "3) 주식 거래 방법", heading="주식 거래 방법"),
        create_chunk(
            1,
            "주식을 거래하려면 증권회사에 계좌를 개설하고 주문을 위탁해야 한다.",
            heading="주식 거래 방법",
        ),
    ]

    merged = merge_short_chunks(chunks)

    assert len(merged) == 1
    assert merged[0].chunk_key == "doc:0"
    assert merged[0].sequence == 0
    assert merged[0].content == (
        "3) 주식 거래 방법\n\n주식을 거래하려면 증권회사에 계좌를 개설하고 주문을 위탁해야 한다."
    )
    assert merged[0].heading == "주식 거래 방법"


def test_merges_multiple_consecutive_short_chunks() -> None:
    chunks = [
        create_chunk(0, "제3장 저축"),
        create_chunk(1, "3.1 저축의 의미"),
        create_chunk(
            2, "저축이란 미래의 소비를 위해 현재의 소비를 줄이는 행위를 말한다."
        ),
    ]

    merged = merge_short_chunks(chunks)

    assert len(merged) == 1
    assert merged[0].content == (
        "제3장 저축\n\n3.1 저축의 의미\n\n저축이란 미래의 소비를 위해 현재의 소비를 줄이는 행위를 말한다."
    )


def test_merges_trailing_short_chunk_backward_when_nothing_follows() -> None:
    chunks = [
        create_chunk(
            0, "정기 예금은 일정 기간 자금을 맡기는 대신 약정 금리를 받는 상품이다."
        ),
        create_chunk(1, "요약"),
    ]

    merged = merge_short_chunks(chunks)

    assert len(merged) == 1
    assert merged[0].chunk_key == "doc:0"
    assert merged[0].content == (
        "정기 예금은 일정 기간 자금을 맡기는 대신 약정 금리를 받는 상품이다.\n\n요약"
    )


def test_keeps_short_chunk_ending_with_period_unmerged() -> None:
    chunks = [
        create_chunk(0, "짧지만 문장이다."),
        create_chunk(1, "다음 문단도 충분히 길고 마침표로 끝나서 유지된다."),
    ]

    merged = merge_short_chunks(chunks)

    assert len(merged) == 2
    assert merged[0].content == "짧지만 문장이다."
    assert merged[1].content == "다음 문단도 충분히 길고 마침표로 끝나서 유지된다."


def test_uses_last_chunk_heading_and_metadata_for_merged_group() -> None:
    chunks = [
        create_chunk(
            0, "3.2 지출", heading="지출", metadata={"section_heading": "지출"}
        ),
        create_chunk(
            1,
            "지출이란 소비를 위해 자금을 사용하는 것을 의미하며 소득과 반대되는 개념이다.",
            heading="지출",
            metadata={"section_heading": "지출"},
        ),
    ]

    merged = merge_short_chunks(chunks)

    assert len(merged) == 1
    assert merged[0].heading == "지출"
    assert merged[0].metadata == {"section_heading": "지출"}


def test_merges_all_chunks_when_entire_document_is_short() -> None:
    chunks = [
        create_chunk(0, "제목"),
        create_chunk(1, "부제목"),
    ]

    merged = merge_short_chunks(chunks)

    assert len(merged) == 1
    assert merged[0].content == "제목\n\n부제목"
    assert merged[0].chunk_key == "doc:0"
