from app.application.ports.chunk_repository import ChunkRepository
from app.domain.newsletter import NewsletterCitation, NewsletterIssueSource


def build_newsletter_issue_sources(
    citations: list[NewsletterCitation],
    chunk_repository: ChunkRepository,
) -> list[NewsletterIssueSource]:
    if not citations:
        return []

    chunk_keys = [citation.chunk_key for citation in citations]
    chunks = chunk_repository.find_by_chunk_keys(chunk_keys)
    chunks_by_key = {chunk.chunk_key: chunk for chunk in chunks}

    sources: list[NewsletterIssueSource] = []
    for citation in citations:
        chunk = chunks_by_key.get(citation.chunk_key)
        if chunk is None:
            continue
        sources.append(
            NewsletterIssueSource(
                document_id=int(chunk.document_id),
                chunk_key=chunk.chunk_key,
                source_url=chunk.source_url,
                evidence_text=citation.evidence_text,
            )
        )
    return sources
