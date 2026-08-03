from langchain_openai import OpenAIEmbeddings


class OpenAIEmbeddingClient:
    def __init__(
        self,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._client = OpenAIEmbeddings(
            model=model,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return self._client.embed_documents(texts)

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        return self._client.embed_query(text)
