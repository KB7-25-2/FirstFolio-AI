from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.chunk import DocumentChunk
from app.domain.newsletter import REQUIRED_SECTION_SIZE


def collect_week_news_chunks(
    chunks: Sequence[DocumentChunk],
    week_start_date: date,
) -> list[DocumentChunk]:
    """week_start_date(월요일)부터 그 주 일요일까지 발행된 뉴스 청크만 걸러낸다.

    published_at이 있는 청크만 뉴스로 판별한다(TextbookChunker는 이 값을
    채우지 않는다 — DAILY_NEWS 판별 로직과 동일 기준).
    """
    week_end_date = week_start_date + timedelta(days=7)
    return [
        chunk
        for chunk in chunks
        if chunk.published_at is not None
        and week_start_date <= chunk.published_at.date() < week_end_date
    ]


@dataclass(frozen=True, slots=True)
class NewsletterIssueCandidate:
    """이슈 선정 결과 하나 — 기사(document_id) 단위로 묶은 청크 그룹."""

    document_id: str
    title: str
    published_at: datetime
    chunks: tuple[DocumentChunk, ...]


def select_top_issue_candidates(
    chunks: Sequence[DocumentChunk],
    count: int = REQUIRED_SECTION_SIZE,
) -> list[NewsletterIssueCandidate]:
    """기사 단위로 묶고, 청크 수가 많은(내용이 풍부한) 기사를 우선 선정한다.

    ⚠️ 임시 중요도 지표: 조회수·편집 우선순위 같은 실제 신호가 아직 없어
    기사당 청크 개수(분량)를 대리 지표로 쓴다. 더 나은 신호가 생기면 교체할 것.
    동률이면 최신 발행일을 우선한다.
    """
    articles: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        if chunk.published_at is None:
            continue
        articles.setdefault(chunk.document_id, []).append(chunk)

    candidates = [
        NewsletterIssueCandidate(
            document_id=document_id,
            title=group[0].title,
            published_at=group[0].published_at,
            chunks=tuple(sorted(group, key=lambda c: c.sequence)),
        )
        for document_id, group in articles.items()
    ]
    candidates.sort(
        key=lambda candidate: (len(candidate.chunks), candidate.published_at),
        reverse=True,
    )
    return candidates[:count]
