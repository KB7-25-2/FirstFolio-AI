import math
from collections.abc import Sequence

from app.application.ports.embedding import EmbeddingClient


def find_semantic_duplicate(
    prompt: str,
    existing_prompts: Sequence[str],
    embedding_client: EmbeddingClient,
    threshold: float,
) -> str | None:
    """표현만 다르고 의미가 같은 기존 문항을 찾는다.

    완전일치 중복 검사(normalize_quiz_prompt)는 표현을 바꾼 사실상 동일
    문항을 잡지 못한다. 임베딩 코사인 유사도가 threshold 이상인 기존
    문항이 있으면 그 문항 원문을 반환하고, 없으면 None을 반환한다.
    """
    if not existing_prompts:
        return None

    prompt_vector = embedding_client.embed_query(prompt)
    existing_vectors = embedding_client.embed_documents(list(existing_prompts))

    for existing_prompt, existing_vector in zip(
        existing_prompts,
        existing_vectors,
        strict=True,
    ):
        if _cosine_similarity(prompt_vector, existing_vector) >= threshold:
            return existing_prompt

    return None


def _cosine_similarity(
    a: Sequence[float],
    b: Sequence[float],
) -> float:
    dot_product = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)
