from datetime import datetime

import pytest

from app.application.ports.chunk_repository import ChunkNotFoundError
from app.application.quiz_sources import build_quiz_sources
from app.domain.chunk import DocumentChunk
from app.domain.quiz import Quiz
from app.infrastructure.repositories.in_memory_chunk import InMemoryChunkRepository


def _quiz(
    citations: list[dict[str, str]] | None = None,
) -> Quiz:
    return Quiz.model_validate(
        {
            "usage_type": "SUB_CHAPTER",
            "question_type": "SINGLE_CHOICE",
            "prompt": "예금에 대한 설명으로 옳은 것은?",
            "scenario_json": None,
            "options": [
                {"option_id": "1", "text": "선택지 1"},
                {"option_id": "2", "text": "선택지 2"},
                {"option_id": "3", "text": "선택지 3"},
                {"option_id": "4", "text": "선택지 4"},
            ],
            "correct_answer": {"option_id": "1"},
            "explanation": "예금은 금융기관에 돈을 맡기는 금융상품이다.",
            "difficulty": "EASY",
            "citations": citations
            if citations is not None
            else [
                {
                    "chunk_key": "47:37",
                    "evidence_text": ("예금은 금융기관에 돈을 맡기는 금융상품이다."),
                },
                {
                    "chunk_key": "47:38",
                    "evidence_text": "예금은 약정된 이자를 받을 수 있다.",
                },
            ],
        }
    )


def _repository() -> InMemoryChunkRepository:
    repository = InMemoryChunkRepository()
    repository.save_all(
        [
            DocumentChunk(
                document_id="47",
                chunk_key="47:37",
                sequence=37,
                content="예금은 금융기관에 돈을 맡기는 금융상품이다.",
                title="금융 교과서",
                source="financial_textbook.txt",
                heading="저축과 저축 상품",
                source_url=None,
                published_at=None,
            ),
            DocumentChunk(
                document_id="47",
                chunk_key="47:38",
                sequence=38,
                content="예금은 약정된 이자를 받을 수 있다.",
                title="금융 교과서",
                source="https://example.com/textbook",
                heading=None,
                source_url="https://example.com/textbook",
                published_at=datetime(2026, 8, 3, 9, 0),
            ),
        ]
    )
    return repository


def test_build_sources_in_citation_order() -> None:
    sources = build_quiz_sources(
        quiz=_quiz(),
        chunk_repository=_repository(),
    )

    assert [source.chunk_key for source in sources] == [
        "47:37",
        "47:38",
    ]
    assert sources[0].document_id == 47
    assert sources[0].title == "금융 교과서"
    assert sources[0].heading == "저축과 저축 상품"
    assert sources[0].source_url is None
    assert sources[0].published_at is None
    assert sources[0].evidence_text == ("예금은 금융기관에 돈을 맡기는 금융상품이다.")
    assert sources[1].source_url == "https://example.com/textbook"
    assert sources[1].published_at == datetime(2026, 8, 3, 9, 0)


def test_return_empty_sources_without_repository_lookup() -> None:
    repository = InMemoryChunkRepository()

    sources = build_quiz_sources(
        quiz=_quiz(citations=[]),
        chunk_repository=repository,
    )

    assert sources == []


def test_propagate_missing_citation_chunk_error() -> None:
    with pytest.raises(
        ChunkNotFoundError,
        match="47:99",
    ):
        build_quiz_sources(
            quiz=_quiz(
                citations=[
                    {
                        "chunk_key": "47:99",
                        "evidence_text": "존재하지 않는 근거",
                    }
                ]
            ),
            chunk_repository=_repository(),
        )
