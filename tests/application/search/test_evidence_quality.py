from app.application.search.evidence_quality import (
    evaluate_evidence_quality,
    evaluate_evidence_quality_for_topics,
)
from app.domain.chunk import DocumentChunk


def create_chunk(
    chunk_key: str,
    content: str,
) -> DocumentChunk:
    document_id = chunk_key.split(":")[0]
    return DocumentChunk(
        document_id=document_id,
        chunk_key=chunk_key,
        sequence=0,
        content=content,
        title="금융 교과서",
        source=f"{document_id}.txt",
    )


def test_count_usable_evidence_as_long_sentence_ending_chunks() -> None:
    chunks = [
        create_chunk(
            "97:0",
            "정기 예금은 일정 기간 자금을 맡기는 대신 약정 금리를 받는 상품이다. "
            "중도 해지 시에는 약정 금리보다 낮은 금리가 적용된다.",
        ),
        create_chunk("97:1", "3) 주식 거래 방법"),
    ]

    metrics = evaluate_evidence_quality(
        topic="예금과 적금의 차이",
        retrieved_chunks=chunks,
    )

    assert metrics.topic == "예금과 적금의 차이"
    assert metrics.retrieved_count == 2
    assert metrics.usable_evidence_count == 1
    assert metrics.heading_fragment_count == 1


def test_flag_numbered_headings_as_fragments_even_if_long() -> None:
    chunks = [
        create_chunk(
            "84:0",
            "4.3 주식 투자와 주식시장의 구조 및 매매 절차에 대한 상세한 안내와 설명",
        ),
    ]

    metrics = evaluate_evidence_quality(
        topic="주식 거래 절차",
        retrieved_chunks=chunks,
    )

    assert metrics.heading_fragment_count == 1
    assert metrics.usable_evidence_count == 0


def test_count_distinct_evidence_after_whitespace_normalization() -> None:
    chunks = [
        create_chunk(
            "84:79",
            "주식은 주식시장에서 발행되어 거래가 이루어진다.",
        ),
        create_chunk(
            "98:45",
            "주식은  주식시장에서  발행되어  거래가  이루어진다.",
        ),
        create_chunk(
            "84:93",
            "채권은 발행자에게 돈을 빌려주고 이자를 받는 상품이다.",
        ),
    ]

    metrics = evaluate_evidence_quality(
        topic="주식 거래 절차",
        retrieved_chunks=chunks,
    )

    assert metrics.retrieved_count == 3
    assert metrics.distinct_evidence_count == 2


def test_return_zero_counts_for_empty_retrieval() -> None:
    metrics = evaluate_evidence_quality(
        topic="검색 결과 없음",
        retrieved_chunks=[],
    )

    assert metrics.retrieved_count == 0
    assert metrics.usable_evidence_count == 0
    assert metrics.distinct_evidence_count == 0
    assert metrics.heading_fragment_count == 0


def test_evaluate_evidence_quality_for_multiple_topics() -> None:
    usable_chunk = create_chunk(
        "97:0",
        "정기 예금은 일정 기간 자금을 맡기는 대신 약정 금리를 받는 상품이다. "
        "중도 해지 시에는 약정 금리보다 낮은 금리가 적용된다.",
    )
    heading_chunk = create_chunk("97:1", "3) 주식 거래 방법")

    results = evaluate_evidence_quality_for_topics(
        {
            "예금과 적금의 차이": [usable_chunk],
            "주식 거래 절차": [heading_chunk],
        }
    )

    metrics_by_topic = {metrics.topic: metrics for metrics in results}
    assert metrics_by_topic["예금과 적금의 차이"].usable_evidence_count == 1
    assert metrics_by_topic["주식 거래 절차"].heading_fragment_count == 1
