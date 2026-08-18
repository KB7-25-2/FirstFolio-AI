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
from app.infrastructure.openai_news_summary import OpenAINewsSummarizer
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
_MAX_CANDIDATES_MULTIPLIER = 4


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


def summarize(summarizer: OpenAINewsSummarizer, title: str, description: str) -> str:
    try:
        return summarizer.summarize(title, description)
    except Exception:
        return description


def to_payload(
    item: NaverNewsItem, image_url: str | None, summary: str
) -> NewsArticlePayload:
    source_url = item.originallink or item.link
    return NewsArticlePayload(
        title=clean_text(item.title),
        summary=summary,
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
    summarizer = OpenAINewsSummarizer(
        model=runtime_settings.generation_model,
        timeout_seconds=runtime_settings.openai_timeout_seconds,
        max_retries=runtime_settings.openai_max_retries,
    )

    max_candidates = display * _MAX_CANDIDATES_MULTIPLIER
    collected: list[tuple[NaverNewsItem, str]] = []
    checked = 0
    start = 1

    with httpx.Client() as scrape_client:
        while len(collected) < display and checked < max_candidates:
            items = naver_client.search(query, display=display, start=start)
            if not items:
                break

            for item in items:
                checked += 1
                source_url = item.originallink or item.link
                image_url = fetch_og_image(scrape_client, source_url)
                if image_url:
                    collected.append((item, image_url))
                    if len(collected) >= display:
                        break
                if checked >= max_candidates:
                    break

            start += display

        results = []
        for item, image_url in collected:
            title = clean_text(item.title)
            summary = summarize(summarizer, title, clean_text(item.description))
            payload = to_payload(item, image_url, summary)
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
