import argparse
import html
import json
import re
import sys
from collections.abc import Sequence
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.naver_news_client import NaverNewsClient, NaverNewsItem
from app.infrastructure.spring_news_api_client import (
    NewsArticlePayload,
    SpringNewsApiClient,
)

_TAG_PATTERN = re.compile(r"</?b>")
_META_TAG_PATTERN = re.compile(r"<meta\s+[^>]*>", re.IGNORECASE)
_PROPERTY_OG_IMAGE_PATTERN = re.compile(r'property=["\']og:image["\']', re.IGNORECASE)
_CONTENT_ATTR_PATTERN = re.compile(r'content=["\']([^"\']+)["\']', re.IGNORECASE)

_DEFAULT_DISPLAY = 10
_OG_IMAGE_TIMEOUT_SECONDS = 5.0


def clean_text(text: str) -> str:
    return html.unescape(_TAG_PATTERN.sub("", text)).strip()


def extract_og_image(html_text: str) -> str | None:
    for tag in _META_TAG_PATTERN.findall(html_text):
        if _PROPERTY_OG_IMAGE_PATTERN.search(tag):
            match = _CONTENT_ATTR_PATTERN.search(tag)
            if match:
                return match.group(1)
    return None


def fetch_og_image(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(
            url, timeout=_OG_IMAGE_TIMEOUT_SECONDS, follow_redirects=True
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    return extract_og_image(response.text)


def to_payload(item: NaverNewsItem, image_url: str | None) -> NewsArticlePayload:
    source_url = item.originallink or item.link
    return NewsArticlePayload(
        title=clean_text(item.title),
        summary=clean_text(item.description),
        image_url=image_url,
        source_name=urlparse(source_url).netloc,
        source_url=source_url,
        source_published_at=parsedate_to_datetime(item.pub_date),
    )


def run_naver_news_ingest(
    query: str,
    *,
    display: int = _DEFAULT_DISPLAY,
    settings: Settings | None = None,
) -> list[dict[str, object]]:
    runtime_settings = settings or Settings()

    naver_client = NaverNewsClient(
        client_id=runtime_settings.naver_client_id,
        client_secret=runtime_settings.naver_client_secret.get_secret_value(),
    )
    spring_client = SpringNewsApiClient(
        base_url=runtime_settings.spring_internal_base_url,
        internal_token=runtime_settings.spring_internal_token.get_secret_value(),
    )

    items = naver_client.search(query, display=display)

    results = []
    with httpx.Client() as scrape_client:
        for item in items:
            source_url = item.originallink or item.link
            image_url = fetch_og_image(scrape_client, source_url)
            payload = to_payload(item, image_url)
            results.append(spring_client.create_article(payload))

    return results


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="네이버 뉴스 검색 API로 금융 뉴스를 가져와 BE 내부 API로 등록합니다.",
    )
    parser.add_argument("--query", required=True, help="네이버 뉴스 검색어")
    parser.add_argument(
        "--display",
        type=int,
        default=_DEFAULT_DISPLAY,
        help="가져올 기사 수 (기본 10, 최대 100)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)

    try:
        results = run_naver_news_ingest(arguments.query, display=arguments.display)
    except (httpx.HTTPError, ValidationError, ValueError) as error:
        print(
            json.dumps(
                {"stage": "naver_news_ingest", "error": str(error)}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 1

    summary = {
        "sent": len(results),
        "financial_news_ids": [item.get("financial_news_id") for item in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
