from langchain_openai import OpenAIEmbeddings


class OpenAIEmbeddingClient:
    def __init__(
        self,
        model: str,
    ) -> None:
        self._client = OpenAIEmbeddings(model=model)

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
