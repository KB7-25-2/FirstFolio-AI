from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict

_NEWS_PATH = "/api/internal/news"


class NewsArticlePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    image_url: str | None = None
    source_name: str
    source_url: str
    source_published_at: datetime
    published_at: datetime | None = None


class SpringNewsApiClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"X-Internal-Token": internal_token},
            transport=transport,
        )

    def create_article(self, article: NewsArticlePayload) -> dict[str, object]:
        response = self._client.post(
            _NEWS_PATH,
            json=article.model_dump(mode="json", exclude_none=True),
        )
        response.raise_for_status()
        payload = response.json()
        return payload["data"]
