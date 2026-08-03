from unittest.mock import Mock

import pytest

from app.infrastructure import openai_embedding
from app.infrastructure.openai_embedding import OpenAIEmbeddingClient


def test_delegate_embedding_requests_to_langchain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    langchain_client = Mock()
    langchain_client.embed_documents.return_value = [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]
    langchain_client.embed_query.return_value = [0.7, 0.8, 0.9]
    created_client_options: list[dict[str, object]] = []

    def create_embedding_client(
        *,
        model: str,
        timeout: float,
        max_retries: int,
    ) -> Mock:
        created_client_options.append(
            {
                "model": model,
                "timeout": timeout,
                "max_retries": max_retries,
            }
        )
        return langchain_client

    monkeypatch.setattr(
        openai_embedding,
        "OpenAIEmbeddings",
        create_embedding_client,
    )

    client = OpenAIEmbeddingClient(
        model="text-embedding-3-small",
        timeout_seconds=45.0,
        max_retries=3,
    )
    texts = [
        "예금은 금융상품이다.",
        "채권은 이자를 받을 수 있는 상품이다.",
    ]

    document_vectors = client.embed_documents(texts)
    query_vector = client.embed_query("예금 금리")

    assert created_client_options == [
        {
            "model": "text-embedding-3-small",
            "timeout": 45.0,
            "max_retries": 3,
        }
    ]
    assert document_vectors == [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]
    assert query_vector == [0.7, 0.8, 0.9]
    langchain_client.embed_documents.assert_called_once_with(texts)
    langchain_client.embed_query.assert_called_once_with("예금 금리")
