import httpx
from pydantic import BaseModel, ConfigDict

_SEARCH_PATH = "/search/v1/news"


class NaverNewsItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    originallink: str
    link: str
    description: str
    pub_date: str


class NaverNewsClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = "https://naverapihub.apigw.ntruss.com",
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={
                "X-NCP-APIGW-API-KEY-ID": client_id,
                "X-NCP-APIGW-API-KEY": client_secret,
            },
            transport=transport,
        )

    def search(
        self, query: str, display: int = 10, start: int = 1
    ) -> list[NaverNewsItem]:
        response = self._client.get(
            _SEARCH_PATH,
            params={
                "query": query,
                "display": display,
                "start": start,
                "sort": "date",
                "format": "json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        return [
            NaverNewsItem.model_validate({**item, "pub_date": item["pubDate"]})
            for item in payload["items"]
        ]
