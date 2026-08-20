from unittest.mock import Mock

from app.application.newsletter_sources import build_newsletter_issue_sources
from app.domain.chunk import DocumentChunk
from app.domain.newsletter import NewsletterCitation


def _chunk(
    document_id: str, chunk_key: str, source_url: str | None = None
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_key=chunk_key,
        sequence=0,
        content="본문",
        title="제목",
        source="source.txt",
        source_url=source_url,
    )


def test_build_newsletter_issue_sources_resolves_document_id_and_source_url() -> None:
    chunk_repository = Mock()
    chunk_repository.find_by_chunk_keys.return_value = [
        _chunk("47", "47:0", source_url="https://example.com")
    ]
    citations = [
        NewsletterCitation(chunk_key="47:0", evidence_text="근거 문장"),
    ]

    sources = build_newsletter_issue_sources(citations, chunk_repository)

    assert len(sources) == 1
    assert sources[0].document_id == 47
    assert sources[0].chunk_key == "47:0"
    assert sources[0].source_url == "https://example.com"
    assert sources[0].evidence_text == "근거 문장"
    chunk_repository.find_by_chunk_keys.assert_called_once_with(["47:0"])


def test_build_newsletter_issue_sources_skips_unresolved_chunk_keys() -> None:
    chunk_repository = Mock()
    chunk_repository.find_by_chunk_keys.return_value = []
    citations = [NewsletterCitation(chunk_key="99:0", evidence_text="근거 문장")]

    sources = build_newsletter_issue_sources(citations, chunk_repository)

    assert sources == []


def test_build_newsletter_issue_sources_returns_empty_for_no_citations() -> None:
    chunk_repository = Mock()

    sources = build_newsletter_issue_sources([], chunk_repository)

    assert sources == []
    chunk_repository.find_by_chunk_keys.assert_not_called()
