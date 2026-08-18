import json
import sys
from collections.abc import Sequence

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.spring_news_api_client import (
    NewsArticlePayload,
    SpringNewsApiClient,
)

_SAMPLE_ARTICLES: list[dict[str, object]] = [
    {
        "title": "기준금리 동결…예·적금 금리 당분간 유지 전망",
        "summary": "한국은행이 기준금리를 동결하면서 시중은행 예·적금 금리도 당분간 큰 변동 없을 것으로 전망됩니다.",
        "source_name": "경제일보",
        "source_url": "https://example.com/news-manual-1",
        "source_published_at": "2026-08-10T09:00:00",
    },
    {
        "title": "코스피, 반도체주 강세에 2,750선 돌파",
        "summary": "반도체 대형주 강세에 힘입어 코스피가 2,750선을 넘어섰습니다.",
        "source_name": "한국경제",
        "source_url": "https://example.com/news-manual-2",
        "source_published_at": "2026-08-11T14:30:00",
    },
    {
        "title": "청년 정책금융상품 신청 조건 완화",
        "summary": "청년층 대상 정책금융상품의 소득·자산 요건이 완화되어 신청 대상이 넓어집니다.",
        "source_name": "금융감독원",
        "source_url": "https://example.com/news-manual-3",
        "source_published_at": "2026-08-12T08:00:00",
    },
    {
        "title": "채권형 펀드로 자금 이동 지속",
        "summary": "금리 변동성 확대로 안전자산 선호 심리가 커지며 채권형 펀드로 자금 유입이 이어지고 있습니다.",
        "source_name": "머니투데이",
        "source_url": "https://example.com/news-manual-4",
        "source_published_at": "2026-08-13T10:15:00",
    },
    {
        "title": "환율 변동성 확대…수출기업 환헤지 관심 증가",
        "summary": "원/달러 환율 변동성이 커지면서 수출기업들의 환헤지 상품 가입이 늘고 있습니다.",
        "source_name": "서울경제",
        "source_url": "https://example.com/news-manual-5",
        "source_published_at": "2026-08-14T11:45:00",
    },
    {
        "title": "2030세대 파킹통장 가입 증가",
        "summary": "짧은 기간 자금을 굴리려는 2030세대 사이에서 파킹통장 가입이 늘고 있습니다.",
        "source_name": "이데일리",
        "source_url": "https://example.com/news-manual-6",
        "source_published_at": "2026-08-15T13:20:00",
    },
]


def run_news_manual_send(
    *,
    articles: Sequence[dict[str, object]] = _SAMPLE_ARTICLES,
    settings: Settings | None = None,
) -> list[dict[str, object]]:
    runtime_settings = settings or Settings()

    api_client = SpringNewsApiClient(
        base_url=runtime_settings.spring_internal_base_url,
        internal_token=runtime_settings.spring_internal_token.get_secret_value(),
    )

    results = []
    for raw_article in articles:
        payload = NewsArticlePayload.model_validate(raw_article)
        results.append(api_client.create_article(payload))

    return results


def main(argv: Sequence[str] | None = None) -> int:
    del argv

    try:
        results = run_news_manual_send()
    except (httpx.HTTPError, ValidationError, ValueError) as error:
        print(
            json.dumps(
                {"stage": "news_manual_send", "error": str(error)}, ensure_ascii=False
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
