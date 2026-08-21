from unittest.mock import Mock

from app.application.ports.embedding import EmbeddingClient
from app.application.quiz_deduplication import find_semantic_duplicate


def test_return_none_when_no_existing_prompts() -> None:
    embedding_client = Mock(spec=EmbeddingClient)

    result = find_semantic_duplicate(
        "새 문항",
        [],
        embedding_client,
        0.9,
    )

    assert result is None
    embedding_client.embed_query.assert_not_called()
    embedding_client.embed_documents.assert_not_called()


def test_return_matched_prompt_when_similarity_meets_threshold() -> None:
    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_query.return_value = [1.0, 0.0]
    embedding_client.embed_documents.return_value = [[1.0, 0.0], [0.0, 1.0]]

    result = find_semantic_duplicate(
        "정기 예금의 특징으로 옳은 것은?",
        ["예금의 특징으로 맞는 것은?", "채권의 특징으로 맞는 것은?"],
        embedding_client,
        0.9,
    )

    assert result == "예금의 특징으로 맞는 것은?"
    embedding_client.embed_query.assert_called_once_with(
        "정기 예금의 특징으로 옳은 것은?"
    )
    embedding_client.embed_documents.assert_called_once_with(
        ["예금의 특징으로 맞는 것은?", "채권의 특징으로 맞는 것은?"]
    )


def test_return_none_when_similarity_below_threshold() -> None:
    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_query.return_value = [1.0, 0.0]
    embedding_client.embed_documents.return_value = [[0.0, 1.0]]

    result = find_semantic_duplicate(
        "새 문항",
        ["전혀 다른 문항"],
        embedding_client,
        0.9,
    )

    assert result is None


def test_return_none_when_all_below_threshold_even_if_some_similar() -> None:
    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_query.return_value = [1.0, 0.0]
    embedding_client.embed_documents.return_value = [[0.8, 0.6]]

    result = find_semantic_duplicate(
        "새 문항",
        ["약간 비슷한 문항"],
        embedding_client,
        0.95,
    )

    assert result is None


def test_return_zero_similarity_for_zero_vector_instead_of_error() -> None:
    embedding_client = Mock(spec=EmbeddingClient)
    embedding_client.embed_query.return_value = [0.0, 0.0]
    embedding_client.embed_documents.return_value = [[1.0, 0.0]]

    result = find_semantic_duplicate(
        "새 문항",
        ["기존 문항"],
        embedding_client,
        0.1,
    )

    assert result is None
