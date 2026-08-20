from datetime import date, datetime

from app.application.newsletter_collection import (
    collect_week_news_chunks,
    select_top_issue_candidates,
)
from app.domain.chunk import DocumentChunk

MONDAY = date(2026, 8, 17)


def _chunk(
    document_id: str,
    sequence: int,
    title: str,
    published_at: datetime | None,
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_key=f"{document_id}:{sequence}",
        sequence=sequence,
        content=f"{title} 본문 {sequence}",
        title=title,
        source=f"{title}.txt",
        published_at=published_at,
    )


def test_collect_week_news_chunks_includes_monday_through_sunday() -> None:
    chunks = [
        _chunk("1", 0, "월요일 기사", datetime(2026, 8, 17, 9, 0)),
        _chunk("2", 0, "일요일 기사", datetime(2026, 8, 23, 23, 59)),
    ]

    result = collect_week_news_chunks(chunks, MONDAY)

    assert len(result) == 2


def test_collect_week_news_chunks_excludes_previous_and_next_week() -> None:
    chunks = [
        _chunk("1", 0, "지난주 일요일", datetime(2026, 8, 16, 23, 59)),
        _chunk("2", 0, "다음주 월요일", datetime(2026, 8, 24, 0, 0)),
    ]

    result = collect_week_news_chunks(chunks, MONDAY)

    assert result == []


def test_collect_week_news_chunks_excludes_non_news_chunks() -> None:
    chunks = [_chunk("1", 0, "교과서 문단", None)]

    result = collect_week_news_chunks(chunks, MONDAY)

    assert result == []


def test_select_top_issue_candidates_prefers_articles_with_more_chunks() -> None:
    chunks = [
        _chunk("101", 0, "짧은 기사", datetime(2026, 8, 17, 9, 0)),
        _chunk("102", 0, "긴 기사", datetime(2026, 8, 17, 9, 0)),
        _chunk("102", 1, "긴 기사", datetime(2026, 8, 17, 9, 0)),
        _chunk("102", 2, "긴 기사", datetime(2026, 8, 17, 9, 0)),
    ]

    candidates = select_top_issue_candidates(chunks, count=2)

    assert candidates[0].document_id == "102"
    assert len(candidates[0].chunks) == 3
    assert candidates[1].document_id == "101"


def test_select_top_issue_candidates_breaks_ties_by_latest_published_at() -> None:
    chunks = [
        _chunk("101", 0, "이전 기사", datetime(2026, 8, 17, 9, 0)),
        _chunk("102", 0, "최신 기사", datetime(2026, 8, 19, 9, 0)),
    ]

    candidates = select_top_issue_candidates(chunks, count=1)

    assert candidates[0].document_id == "102"


def test_select_top_issue_candidates_returns_fewer_when_not_enough_articles() -> None:
    chunks = [_chunk("101", 0, "기사", datetime(2026, 8, 17, 9, 0))]

    candidates = select_top_issue_candidates(chunks, count=3)

    assert len(candidates) == 1


def test_select_top_issue_candidates_excludes_chunks_without_published_at() -> None:
    chunks = [_chunk("101", 0, "교과서 문단", None)]

    candidates = select_top_issue_candidates(chunks, count=3)

    assert candidates == []


def test_select_top_issue_candidates_orders_chunks_by_sequence() -> None:
    chunks = [
        _chunk("101", 2, "기사", datetime(2026, 8, 17, 9, 0)),
        _chunk("101", 0, "기사", datetime(2026, 8, 17, 9, 0)),
        _chunk("101", 1, "기사", datetime(2026, 8, 17, 9, 0)),
    ]

    candidates = select_top_issue_candidates(chunks, count=1)

    assert [chunk.sequence for chunk in candidates[0].chunks] == [0, 1, 2]
