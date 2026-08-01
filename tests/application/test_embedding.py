from langchain_core.embeddings import DeterministicFakeEmbedding

from app.application.ports.embedding import EmbeddingClient


def test_create_document_embeddings_without_external_api() -> None:
    client: EmbeddingClient = DeterministicFakeEmbedding(size=3)
    texts = [
        "예금은 돈을 맡기는 금융상품이다.",
        "채권은 돈을 빌려주고 이자를 받는 상품이다.",
    ]

    first_vectors = client.embed_documents(texts)
    second_vectors = client.embed_documents(texts)

    assert first_vectors == second_vectors
    assert len(first_vectors) == 2
    assert all(len(vector) == 3 for vector in first_vectors)


def test_create_same_embedding_for_same_query() -> None:
    client: EmbeddingClient = DeterministicFakeEmbedding(size=3)

    first_vector = client.embed_query("예금 금리")
    second_vector = client.embed_query("예금 금리")

    assert first_vector == second_vector
    assert len(first_vector) == 3
