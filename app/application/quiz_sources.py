from app.application.ports.chunk_repository import ChunkRepository
from app.domain.quiz import Quiz, QuizSource


def build_quiz_sources(
    quiz: Quiz,
    chunk_repository: ChunkRepository,
) -> list[QuizSource]:
    if not quiz.citations:
        return []

    chunk_keys = [citation.chunk_key for citation in quiz.citations]
    chunks = chunk_repository.find_by_chunk_keys(chunk_keys)

    return [
        QuizSource(
            document_id=int(chunk.document_id),
            chunk_key=chunk.chunk_key,
            title=chunk.title,
            heading=chunk.heading,
            source_url=chunk.source_url,
            published_at=chunk.published_at,
            evidence_text=citation.evidence_text,
        )
        for citation, chunk in zip(
            quiz.citations,
            chunks,
            strict=True,
        )
    ]
